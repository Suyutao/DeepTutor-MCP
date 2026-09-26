#!/usr/bin/env python3
"""Small, dependency-free MCP bridge to a DeepTutor server."""

import json
import asyncio
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


def setting(name, default=""):
    return os.environ.get(name, default).strip()


BASE_URL = setting("DEEPTUTOR_BASE_URL").rstrip("/")
TIMEOUT = float(setting("DEEPTUTOR_TIMEOUT", "20"))
TOKEN = setting("DEEPTUTOR_TOKEN")
TOKEN_FILE = setting("DEEPTUTOR_TOKEN_FILE")
SSH_TARGET = setting("DEEPTUTOR_SSH_TARGET")
REMOTE_CLI = setting("DEEPTUTOR_REMOTE_CLI", "deeptutor")
REMOTE_HOME = setting("DEEPTUTOR_REMOTE_HOME")
DEFAULT_TIMEZONE = setting("DEEPTUTOR_MCP_TIMEZONE", "Asia/Shanghai")


def http(method, path, *, query=None, body=None):
    if not BASE_URL:
        raise ValueError("Set DEEPTUTOR_BASE_URL to the DeepTutor API origin")
    if urllib.parse.urlsplit(BASE_URL).scheme not in ("http", "https"):
        raise ValueError("DEEPTUTOR_BASE_URL must use http or https")
    url = BASE_URL + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    headers = {"Accept": "application/json"}
    token = TOKEN
    if TOKEN_FILE:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            token = f.read().strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    # Local/LAN DeepTutor addresses must not leak through a shell proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            raw = response.read()
            return json.loads(raw) if raw else {"status": response.status}
    except urllib.error.HTTPError as exc:
        detail = exc.read(1500).decode("utf-8", "replace")
        raise RuntimeError(f"DeepTutor HTTP {exc.code}: {detail}") from exc


def http_text(path, *, max_bytes=4_000_000):
    if not BASE_URL:
        raise ValueError("Set DEEPTUTOR_BASE_URL to the DeepTutor API origin")
    headers = {"Accept": "text/plain"}
    token = TOKEN
    if TOKEN_FILE:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            token = f.read().strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(BASE_URL + path, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            raw = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read(1500).decode("utf-8", "replace")
        raise RuntimeError(f"DeepTutor HTTP {exc.code}: {detail}") from exc
    if len(raw) > max_bytes:
        raise ValueError("Source text is over 4 MB; choose a smaller source file")
    return raw.decode("utf-8", "replace")


def segment(value):
    value = str(value).strip()
    if not value or "/" in value or "?" in value or "#" in value:
        raise ValueError("Invalid resource id")
    return urllib.parse.quote(value, safe="")


def file_path(value):
    value = str(value).strip()
    parts = value.split("/")
    if not value or any(part in ("", ".", "..") for part in parts) or "?" in value or "#" in value:
        raise ValueError("Invalid knowledge base file path")
    return urllib.parse.quote(value, safe="/")


def clipped_text(value, offset=0, limit=12000):
    offset = max(int(offset), 0)
    limit = min(max(int(limit), 1), 24000)
    return {"text": value[offset:offset + limit], "offset": offset, "total_chars": len(value), "has_more": offset + limit < len(value)}


def required(args, *keys):
    for key in keys:
        if key not in args or args[key] is None or args[key] == "":
            raise ValueError(f"Missing required argument: {key}")


def confirmed(args):
    if args.get("confirm") is not True:
        raise ValueError("Set confirm=true after reviewing the proposed change")


def run_turn(args):
    if not SSH_TARGET:
        raise ValueError("Set DEEPTUTOR_SSH_TARGET to enable DeepTutor capability turns")
    required(args, "capability", "message")
    if args.get("direct_dt_conversation") is not True:
        raise ValueError("Use this only for an explicit request to converse directly with DeepTutor")
    capability = args["capability"]
    if not isinstance(capability, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", capability):
        raise ValueError("Invalid capability name")
    argv = [REMOTE_CLI, "run", capability, args["message"], "--format", "json"]
    if args.get("session_id"):
        argv += ["--session", args["session_id"]]
    if args.get("knowledge_base"):
        argv += ["--kb", args["knowledge_base"]]
    command = shlex.join(argv)
    if REMOTE_HOME:
        command = "DEEPTUTOR_HOME=" + shlex.quote(REMOTE_HOME) + " " + command
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", SSH_TARGET, command],
        capture_output=True, text=True, timeout=float(setting("DEEPTUTOR_TURN_TIMEOUT", "240")),
    )
    events = []
    for line in proc.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    if proc.returncode or not events:
        raise RuntimeError(f"DeepTutor turn failed ({proc.returncode}): {proc.stderr[-800:]}")
    done = next((e for e in reversed(events) if e.get("type") == "done"), {})
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    return {
        "session_id": done.get("session_id"),
        "turn_id": done.get("turn_id"),
        "status": done.get("metadata", {}).get("status"),
        "answer": result.get("metadata", {}).get("response") or "".join(e.get("content", "") for e in events if e.get("type") == "content"),
        "errors": [e for e in events if e.get("type") == "error"],
    }


def dispatch(name, args):
    if name == "search_vector_knowledge":
        return vector_search(args)
    if name == "deeptutor_status":
        health = http("GET", "/health/ready")
        spec = http("GET", "/openapi.json")
        return {"health": health, "api_title": spec.get("info", {}).get("title"), "path_count": len(spec.get("paths", {})), "base_url": BASE_URL}
    if name == "list_deeptutor_capabilities":
        return http("GET", "/api/capabilities/registered")
    if name == "learning_overview":
        return {
            "courses": http("GET", "/api/courses").get("courses", []),
            "mastery": http("GET", "/api/mastery-paths/progress"),
            "practice": http("GET", "/api/question-notebook/practice/summary", query={"timezone": args.get("timezone", DEFAULT_TIMEZONE)}),
        }
    if name == "list_courses":
        return http("GET", "/api/courses")
    if name == "get_course_state":
        required(args, "course_id")
        return http("GET", "/api/courses/" + segment(args["course_id"]) + "/state")
    if name == "list_course_resource_candidates":
        return http("GET", "/api/courses/resource-candidates")
    if name == "replace_course_syllabus":
        required(args, "course_id", "units")
        confirmed(args)
        if not isinstance(args["units"], list):
            raise ValueError("units must be an array")
        return http("PUT", "/api/courses/" + segment(args["course_id"]) + "/syllabus", body={"units": args["units"]})
    if name == "set_course_unit_covered":
        required(args, "course_id", "unit_id", "covered")
        confirmed(args)
        return http("PATCH", "/api/courses/" + segment(args["course_id"]) + "/syllabus/" + segment(args["unit_id"]), body={"covered": args["covered"]})
    if name == "attach_course_resource":
        required(args, "course_id", "kind", "ref_id")
        confirmed(args)
        return http("POST", "/api/courses/" + segment(args["course_id"]) + "/resources", body={k: args[k] for k in ("kind", "ref_id", "label") if k in args})
    if name == "list_mastery_paths":
        topics = http("GET", "/api/mastery-paths/topics").get("topics", [])
        summaries = []
        for topic in topics:
            path_map = topic.get("map") or {}
            next_step = topic.get("next") or {}
            summaries.append({
                "path_id": topic.get("path_id"),
                "name": topic.get("name"),
                "counts": path_map.get("counts") or {},
                "due_reviews": path_map.get("due_reviews", 0),
                "next": {k: next_step.get(k) for k in ("action", "knowledge_point_id", "knowledge_point_name", "module_name")},
                "path_revision": topic.get("path_revision"),
                "updated_at": topic.get("updated_at"),
            })
        return {"total": len(summaries), "topics": summaries}
    if name == "get_mastery_path":
        required(args, "path_id")
        return http("GET", "/api/mastery-paths/topics/" + segment(args["path_id"]))
    if name == "replace_mastery_outline":
        required(args, "path_id", "expected_revision", "modules")
        confirmed(args)
        if not isinstance(args["modules"], list) or not args["modules"]:
            raise ValueError("modules must be a nonempty array")
        path = "/api/mastery-paths/topics/" + segment(args["path_id"])
        before = http("GET", path)
        if before.get("path_revision") != args["expected_revision"]:
            raise ValueError("Mastery path changed; read it again before editing")
        return http("PUT", path + "/map", body={"modules": args["modules"]})
    if name == "get_mastery_review_settings":
        required(args, "path_id")
        return http("GET", "/api/mastery-paths/topics/" + segment(args["path_id"]) + "/review-settings")
    if name == "set_mastery_review_settings":
        required(args, "path_id", "desired_retention")
        confirmed(args)
        return http("PUT", "/api/mastery-paths/topics/" + segment(args["path_id"]) + "/review-settings", body={"desired_retention": args["desired_retention"]})
    if name == "get_mastery_objective":
        required(args, "path_id", "knowledge_point_id")
        return http("GET", "/api/mastery-paths/progress/" + segment(args["path_id"]) + "/objectives/" + segment(args["knowledge_point_id"]))
    if name == "list_mastery_events":
        required(args, "path_id")
        return http("GET", "/api/mastery-paths/progress/" + segment(args["path_id"]) + "/events", query={"after_revision": max(int(args.get("after_revision", 0)), 0)})
    if name == "set_mastery_learner_override":
        required(args, "path_id", "knowledge_point_id", "mastered")
        confirmed(args)
        return http("POST", "/api/mastery-paths/topics/" + segment(args["path_id"]) + "/objectives/" + segment(args["knowledge_point_id"]) + "/override", body={"mastered": args["mastered"], "note": args.get("note", "")})
    if name == "list_question_entries":
        query = {k: args.get(k) for k in ("search", "mistakes_only", "bookmarked", "category_id", "mastery_path_id", "knowledge_point_id", "source", "limit", "offset")}
        query["limit"] = min(max(int(query["limit"] or 20), 1), 100)
        return http("GET", "/api/question-notebook/entries", query=query)
    if name == "get_question_entry":
        required(args, "entry_id")
        return http("GET", "/api/question-notebook/entries/" + segment(args["entry_id"]))
    if name == "upsert_question_entry":
        required(args, "question_id", "question")
        confirmed(args)
        body = {k: args[k] for k in ("question_id", "question", "question_type", "options", "correct_answer", "explanation", "difficulty", "user_answer", "is_correct", "material_title") if k in args}
        body.update({"origin_type": "external_import", "origin_ref": args.get("origin_ref", "codex-mcp"), "source": "import"})
        return http("POST", "/api/question-notebook/entries/upsert", body=body)
    if name == "update_question_entry":
        required(args, "entry_id")
        confirmed(args)
        body = {k: args[k] for k in ("bookmarked", "resolved", "ai_judgment", "followup_session_id") if k in args}
        if not body:
            raise ValueError("No supported fields to update")
        return http("PATCH", "/api/question-notebook/entries/" + segment(args["entry_id"]), body=body)
    if name == "delete_question_entry":
        required(args, "entry_id")
        confirmed(args)
        return http("DELETE", "/api/question-notebook/entries/" + segment(args["entry_id"]))
    if name == "practice_summary":
        return http("GET", "/api/question-notebook/practice/summary", query={"timezone": args.get("timezone", DEFAULT_TIMEZONE), "all_workspaces": args.get("all_workspaces", False)})
    if name == "practice_analytics":
        return http("GET", "/api/question-notebook/practice/analytics", query={"timezone": args.get("timezone", DEFAULT_TIMEZONE), "days": min(max(int(args.get("days", 30)), 1), 90), "course_id": args.get("course_id"), "all_workspaces": args.get("all_workspaces", False)})
    if name == "list_question_categories":
        return http("GET", "/api/question-notebook/categories", query={"course_id": args.get("course_id")})
    if name == "practice_queue":
        return http("GET", "/api/question-notebook/practice/queue", query={"timezone": args.get("timezone", DEFAULT_TIMEZONE), "limit": min(max(int(args.get("limit", 20)), 1), 100), "all_workspaces": args.get("all_workspaces", False)})
    if name == "get_practice_question":
        required(args, "entry_id")
        return http("GET", "/api/question-notebook/practice/questions/" + segment(args["entry_id"]))
    if name == "check_practice_answer":
        required(args, "entry_id", "answer")
        return http("POST", "/api/question-notebook/practice/questions/" + segment(args["entry_id"]) + "/check", body={"answer": args["answer"]})
    if name == "record_practice_review":
        required(args, "entry_id", "request_id", "version", "rating")
        confirmed(args)
        body = {k: args[k] for k in ("request_id", "version", "rating", "answer", "self_report") if k in args}
        return http("POST", "/api/question-notebook/practice/questions/" + segment(args["entry_id"]) + "/review", body=body)
    if name == "list_books":
        return http("GET", "/api/books")
    if name == "get_book_spine":
        required(args, "book_id")
        return http("GET", "/api/books/" + segment(args["book_id"]) + "/spine")
    if name == "get_book_page":
        required(args, "book_id", "page_id")
        return http("GET", "/api/books/" + segment(args["book_id"]) + "/pages/" + segment(args["page_id"]))
    if name == "list_book_learning_captures":
        required(args, "book_id")
        return http("GET", "/api/books/" + segment(args["book_id"]) + "/learning-captures", query={"status": args.get("status")})
    if name == "list_reading_materials":
        return http("GET", "/api/reading/materials")
    if name == "get_reading_material":
        required(args, "material_id")
        return http("GET", "/api/reading/materials/" + segment(args["material_id"]))
    if name == "get_reading_unit":
        required(args, "material_id", "locator")
        result = http("GET", "/api/reading/materials/" + segment(args["material_id"]) + "/units/" + str(int(args["locator"])))
        if isinstance(result.get("text"), str):
            result["text_slice"] = clipped_text(result.pop("text"), args.get("offset", 0), args.get("max_chars", 12000))
        return result
    if name == "list_reading_annotations":
        required(args, "material_id")
        return http("GET", "/api/reading/materials/" + segment(args["material_id"]) + "/annotations")
    if name == "save_reading_annotation":
        required(args, "material_id", "locator", "kind")
        confirmed(args)
        body = {k: args[k] for k in ("annotation_id", "locator", "kind", "color", "quote", "note", "source_anchor") if k in args}
        return http("PUT", "/api/reading/materials/" + segment(args["material_id"]) + "/annotations", body=body)
    if name == "delete_reading_annotation":
        required(args, "material_id", "annotation_id")
        confirmed(args)
        return http("DELETE", "/api/reading/materials/" + segment(args["material_id"]) + "/annotations/" + segment(args["annotation_id"]))
    if name == "list_reading_bookmarks":
        required(args, "material_id")
        return http("GET", "/api/reading/materials/" + segment(args["material_id"]) + "/bookmarks")
    if name == "add_reading_bookmark":
        required(args, "material_id", "locator")
        confirmed(args)
        return http("POST", "/api/reading/materials/" + segment(args["material_id"]) + "/bookmarks", body={k: args[k] for k in ("locator", "label", "source_anchor") if k in args})
    if name == "delete_reading_bookmark":
        required(args, "material_id", "bookmark_id")
        confirmed(args)
        return http("DELETE", "/api/reading/materials/" + segment(args["material_id"]) + "/bookmarks/" + segment(args["bookmark_id"]))
    if name == "list_notebooks":
        return http("GET", "/api/notebooks")
    if name == "get_notebook":
        required(args, "notebook_id")
        return http("GET", "/api/notebooks/" + segment(args["notebook_id"]))
    if name == "create_notebook":
        required(args, "name")
        confirmed(args)
        return http("POST", "/api/notebooks", body={k: args[k] for k in ("name", "description", "color", "icon") if k in args})
    if name == "add_notebook_record":
        required(args, "notebook_id", "title", "user_query", "output", "summary")
        if not str(args["summary"]).strip():
            raise ValueError("A Codex-written summary is required; DeepTutor generates one with its own model if omitted")
        confirmed(args)
        body = {"notebook_ids": [args["notebook_id"]], "record_type": args.get("record_type", "chat"), "title": args["title"], "user_query": args["user_query"], "output": args["output"], "summary": args["summary"], "metadata": {"source": "codex-mcp"}}
        return http("POST", "/api/notebooks/actions/add-record", body=body)
    if name == "update_notebook_record":
        required(args, "notebook_id", "record_id")
        confirmed(args)
        body = {k: args[k] for k in ("title", "summary", "user_query", "output") if k in args}
        if not body:
            raise ValueError("No supported fields to update")
        return http("PUT", "/api/notebooks/" + segment(args["notebook_id"]) + "/records/" + segment(args["record_id"]), body=body)
    if name == "delete_notebook_record":
        required(args, "notebook_id", "record_id")
        confirmed(args)
        return http("DELETE", "/api/notebooks/" + segment(args["notebook_id"]) + "/records/" + segment(args["record_id"]))
    if name == "delete_notebook":
        required(args, "notebook_id")
        confirmed(args)
        return http("DELETE", "/api/notebooks/" + segment(args["notebook_id"]))
    if name == "list_knowledge_bases":
        bases = http("GET", "/api/knowledge-bases")
        return [{k: v for k, v in kb.items() if k in ("id", "name", "is_default", "statistics", "status", "source", "read_only", "available")} for kb in bases]
    if name == "list_knowledge_files":
        required(args, "kb_name")
        files = http("GET", "/api/knowledge-bases/" + segment(args["kb_name"]) + "/files").get("files", [])
        needle = str(args.get("name_contains", "")).casefold()
        suffix = str(args.get("suffix", "")).casefold()
        visible = [f for f in files if f.get("type") == "file" and (args.get("include_hidden") or not any(part.startswith(".") for part in f.get("name", "").split("/"))) and needle in f.get("name", "").casefold() and f.get("name", "").casefold().endswith(suffix)]
        offset = max(int(args.get("offset", 0)), 0)
        limit = min(max(int(args.get("limit", 30)), 1), 100)
        return {"total_matches": len(visible), "offset": offset, "files": visible[offset:offset + limit]}
    if name in ("read_knowledge_file", "search_knowledge_file"):
        required(args, "kb_name", "filename")
        path = "/api/knowledge-bases/" + segment(args["kb_name"]) + "/file-preview-text/" + file_path(args["filename"])
        content = http_text(path)
        if name == "read_knowledge_file":
            return {"kb_name": args["kb_name"], "filename": args["filename"], **clipped_text(content, args.get("offset", 0), args.get("max_chars", 12000))}
        required(args, "query")
        needle = args["query"].casefold()
        haystack = content.casefold()
        pos = 0
        hits = []
        while len(hits) < min(max(int(args.get("limit", 5)), 1), 10):
            pos = haystack.find(needle, pos)
            if pos < 0:
                break
            start = max(0, pos - 160)
            hits.append({"offset": pos, "excerpt": content[start:min(len(content), pos + len(args["query"]) + 240)]})
            pos += max(len(needle), 1)
        return {"kb_name": args["kb_name"], "filename": args["filename"], "query": args["query"], "matches": hits, "source_chars": len(content)}
    if name == "list_deeptutor_sessions":
        return http("GET", "/api/sessions", query={"limit": min(max(int(args.get("limit", 20)), 1), 100), "offset": max(int(args.get("offset", 0)), 0), "all_workspaces": args.get("all_workspaces", False)})
    if name == "get_deeptutor_session":
        required(args, "session_id")
        return http("GET", "/api/sessions/" + segment(args["session_id"]))
    if name == "get_deeptutor_memory_doc":
        required(args, "layer", "key")
        if args["layer"] not in ("L2", "L3"):
            raise ValueError("layer must be L2 or L3")
        return http("GET", "/api/memory/doc/" + segment(args["layer"]) + "/" + segment(args["key"]))
    if name == "send_message_to_deeptutor":
        return run_turn(args)
    raise ValueError("Unknown tool: " + name)


DESTRUCTIVE_TOOLS = {"replace_course_syllabus", "replace_mastery_outline", "delete_question_entry"}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"description": "原始 DeepTutor 工具返回值；其具体字段由对应 DeepTutor API 决定。"}
    },
    "required": ["result"],
    "additionalProperties": False,
}


def tool(name, description, properties=None, required_keys=None):
    properties = properties or {}
    is_write = "confirm" in properties
    if is_write:
        description = (
            "WARNING: Changes stored DeepTutor learning data. Check the target ID and values; "
            "call only when the learner explicitly requests this action. " + description
        )
    return {
        "name": name,
        "description": description,
        "annotations": {"readOnlyHint": not is_write, "destructiveHint": name in DESTRUCTIVE_TOOLS},
        "inputSchema": {"type": "object", "properties": properties, "required": required_keys or [], "additionalProperties": False},
        "outputSchema": OUTPUT_SCHEMA,
    }


S = lambda description, **extra: {"type": "string", "description": description, **extra}
B = lambda description: {"type": "boolean", "description": description}
I = lambda description: {"type": "integer", "description": description}
CONFIRM = {"confirm": B("Set true when this write is authorized by the current user request")}
PATH = {"path_id": S("Mastery path ID")}
ENTRY = {"entry_id": S("Question entry ID")}
COURSE = {"course_id": S("Course ID")}
BOOK = {"book_id": S("Book ID")}
MATERIAL = {"material_id": S("Reading material ID")}
NOTEBOOK = {"notebook_id": S("Notebook ID")}
KB = {"kb_name": S("Knowledge base name")}
VECTOR_TOOL = tool(
    "search_vector_knowledge",
    "Retrieve original indexed passages from one DeepTutor LlamaIndex knowledge base. Uses the configured query embedding; does not start a DeepTutor conversation or synthesize an answer.",
    {
        "kb_name": S("Knowledge base name from list_knowledge_bases"),
        "query": S("Search question or phrase, up to 1000 characters"),
        "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Maximum passages; default 5"},
    },
    ["kb_name", "query"],
)
TOOLS = [
    tool("deeptutor_status", "Check the configured DeepTutor backend and API availability"),
    tool("list_deeptutor_capabilities", "List installed DeepTutor capabilities; informational unless the user directly requests a DeepTutor conversation"),
    tool("learning_overview", "Read courses, mastery summaries and due practice in one request; no DeepTutor model turn", {"timezone": S("IANA timezone; default Asia/Shanghai")}),
    tool("list_courses", "List courses and their syllabus and linked resources"),
    tool("get_course_state", "Read one course's syllabus, resources, sessions, mastery and question statistics", COURSE, ["course_id"]),
    tool("list_course_resource_candidates", "List resources that can be attached to a course"),
    tool("replace_course_syllabus", "Replace a course's full syllabus after review", {**COURSE, "units": {"type": "array", "items": {"type": "object"}, "description": "Complete syllabus units, each with title and optional id, topics and covered"}, **CONFIRM}, ["course_id", "units", "confirm"]),
    tool("set_course_unit_covered", "Mark one syllabus unit covered or uncovered; this is a learner record, not proof of mastery", {**COURSE, "unit_id": S("Syllabus unit ID"), "covered": B("Coverage state"), **CONFIRM}, ["course_id", "unit_id", "covered", "confirm"]),
    tool("attach_course_resource", "Attach an existing book, knowledge base, notebook or other supported resource to a course", {**COURSE, "kind": S("Resource kind from list_course_resource_candidates"), "ref_id": S("Existing resource ID"), "label": S("Display label"), **CONFIRM}, ["course_id", "kind", "ref_id", "confirm"]),
    tool("list_mastery_paths", "List every Mastery Path as a compact summary with total count, progress, next point and due reviews; use get_mastery_path for the full outline"),
    tool("get_mastery_path", "Read one Mastery Path, including outline, revision and reviews", PATH, ["path_id"]),
    tool("replace_mastery_outline", "Replace the full outline after review; preserves IDs supplied in modules and checks revision", {**PATH, "expected_revision": I("Revision read from get_mastery_path"), "modules": {"type": "array", "items": {"type": "object"}, "description": "Complete modules array in DeepTutor ModuleInput shape"}, **CONFIRM}, ["path_id", "expected_revision", "modules", "confirm"]),
    tool("get_mastery_review_settings", "Read a path's desired retention", PATH, ["path_id"]),
    tool("set_mastery_review_settings", "Set desired retention between 0.70 and 0.99", {**PATH, "desired_retention": {"type": "number"}, **CONFIRM}, ["path_id", "desired_retention", "confirm"]),
    tool("get_mastery_objective", "Read one knowledge point's evidence, mastery and review state", {**PATH, "knowledge_point_id": S("Knowledge point ID")}, ["path_id", "knowledge_point_id"]),
    tool("list_mastery_events", "Read recorded changes to a Mastery Path after a revision", {**PATH, "after_revision": I("Read events after this revision; default 0")}, ["path_id"]),
    tool("set_mastery_learner_override", "Record an explicit learner declaration of mastery or non-mastery; never infer this from Codex conversation alone", {**PATH, "knowledge_point_id": S("Knowledge point ID"), "mastered": B("Learner-declared mastery"), "note": S("Learner's reason or evidence"), **CONFIRM}, ["path_id", "knowledge_point_id", "mastered", "confirm"]),
    tool("list_question_entries", "Search and filter DeepTutor's native Question Bank", {"search": S("Question text search"), "mistakes_only": B("Only mistakes"), "bookmarked": B("Only bookmarked"), "category_id": S("Category ID"), "mastery_path_id": S("Mastery path ID"), "knowledge_point_id": S("Knowledge point ID"), "source": S("Question source"), "limit": I("Page size, max 100"), "offset": I("Page offset")}),
    tool("get_question_entry", "Read one native Question Bank entry", ENTRY, ["entry_id"]),
    tool("upsert_question_entry", "Import or update a native Question Bank entry by stable question ID", {"question_id": S("Stable question ID"), "question": S("Question text"), "question_type": S("Question type"), "options": {"type": "object", "additionalProperties": {"type": "string"}}, "correct_answer": S("Reference answer"), "explanation": S("Explanation"), "difficulty": S("Difficulty"), "user_answer": S("Learner's answer"), "is_correct": B("Whether learner was correct"), "material_title": S("Source title"), "origin_ref": S("Source reference"), **CONFIRM}, ["question_id", "question", "confirm"]),
    tool("update_question_entry", "Update supported metadata on one Question Bank entry", {**ENTRY, "bookmarked": B("Bookmark state"), "resolved": B("Resolved state"), "ai_judgment": S("AI judgment note"), "followup_session_id": S("Follow-up session ID"), **CONFIRM}, ["entry_id", "confirm"]),
    tool("delete_question_entry", "Delete one Question Bank entry", {**ENTRY, **CONFIRM}, ["entry_id", "confirm"]),
    tool("practice_summary", "Read Practice counts, due items and next due time", {"timezone": S("IANA timezone, defaults to Asia/Shanghai"), "all_workspaces": B("Include all available workspaces")}),
    tool("practice_queue", "Read due Question Bank practice items", {"timezone": S("IANA timezone, defaults to Asia/Shanghai"), "limit": I("Maximum items, max 100"), "all_workspaces": B("Include all available workspaces")}),
    tool("get_practice_question", "Read a practice question and its review version", ENTRY, ["entry_id"]),
    tool("check_practice_answer", "Check an answer without recording a review", {**ENTRY, "answer": S("Learner's answer")}, ["entry_id", "answer"]),
    tool("record_practice_review", "Record a completed review using the question's current version and a unique request ID", {**ENTRY, "request_id": S("Unique ID, at least 16 URL-safe characters"), "version": I("Version from get_practice_question"), "rating": S("again, hard, good or easy", enum=["again", "hard", "good", "easy"]), "answer": S("Learner's answer"), "self_report": B("True for self-assessed answer"), **CONFIRM}, ["entry_id", "request_id", "version", "rating", "confirm"]),
    tool("practice_analytics", "Read practice trends and source counts for up to 90 days", {"timezone": S("IANA timezone; default Asia/Shanghai"), "days": I("Number of days, max 90"), "course_id": S("Optional course ID"), "all_workspaces": B("Include all available workspaces")}),
    tool("list_question_categories", "List native Question Bank categories", {"course_id": S("Optional course ID")}),
    tool("list_books", "List generated learning books and their status"),
    tool("get_book_spine", "Read a book's chapter and page structure", BOOK, ["book_id"]),
    tool("get_book_page", "Read a generated book page, including source links and blocks", {**BOOK, "page_id": S("Page ID")}, ["book_id", "page_id"]),
    tool("list_book_learning_captures", "List saved learning captures from a book", {**BOOK, "status": S("Optional status filter")}, ["book_id"]),
    tool("list_reading_materials", "List imported reading materials"),
    tool("get_reading_material", "Read one material's outline, units and metadata", MATERIAL, ["material_id"]),
    tool("get_reading_unit", "Read a bounded text slice from one reading unit", {**MATERIAL, "locator": I("One-based unit locator"), "offset": I("Character offset; default 0"), "max_chars": I("Maximum characters; max 24000")}, ["material_id", "locator"]),
    tool("list_reading_annotations", "Read highlights and notes on a material", MATERIAL, ["material_id"]),
    tool("save_reading_annotation", "Create or update a highlight, underline, note or citation on a material", {**MATERIAL, "annotation_id": S("Existing annotation ID to update"), "locator": I("One-based unit locator"), "kind": S("Annotation kind", enum=["highlight", "underline", "note", "citation"]), "color": S("Highlight color"), "quote": S("Quoted source text"), "note": S("Learner's note"), "source_anchor": S("Source anchor"), **CONFIRM}, ["material_id", "locator", "kind", "confirm"]),
    tool("delete_reading_annotation", "Delete one reading annotation", {**MATERIAL, "annotation_id": S("Annotation ID"), **CONFIRM}, ["material_id", "annotation_id", "confirm"]),
    tool("list_reading_bookmarks", "Read bookmarks on a material", MATERIAL, ["material_id"]),
    tool("add_reading_bookmark", "Bookmark a unit in a reading material", {**MATERIAL, "locator": I("One-based unit locator"), "label": S("Bookmark label"), "source_anchor": S("Source anchor"), **CONFIRM}, ["material_id", "locator", "confirm"]),
    tool("delete_reading_bookmark", "Delete one reading bookmark", {**MATERIAL, "bookmark_id": S("Bookmark ID"), **CONFIRM}, ["material_id", "bookmark_id", "confirm"]),
    tool("list_notebooks", "List DeepTutor notebooks"),
    tool("get_notebook", "Read a notebook and its saved records", NOTEBOOK, ["notebook_id"]),
    tool("create_notebook", "Create a DeepTutor notebook", {"name": S("Notebook name"), "description": S("Description"), "color": S("Color"), "icon": S("Icon"), **CONFIRM}, ["name", "confirm"]),
    tool("add_notebook_record", "Save a Codex-produced lesson or note in a DeepTutor notebook; Codex must supply summary to avoid a DeepTutor model call", {**NOTEBOOK, "title": S("Record title"), "user_query": S("Learner question or learning goal"), "output": S("Lesson or note content"), "summary": S("Required summary written by Codex"), "record_type": S("DeepTutor record type", enum=["chat", "question", "research", "solve", "reading"]), **CONFIRM}, ["notebook_id", "title", "user_query", "output", "summary", "confirm"]),
    tool("update_notebook_record", "Edit a saved notebook record", {**NOTEBOOK, "record_id": S("Record ID"), "title": S("New title"), "summary": S("New summary"), "user_query": S("New query"), "output": S("New content"), **CONFIRM}, ["notebook_id", "record_id", "confirm"]),
    tool("delete_notebook_record", "Delete a notebook record", {**NOTEBOOK, "record_id": S("Record ID"), **CONFIRM}, ["notebook_id", "record_id", "confirm"]),
    tool("delete_notebook", "Delete an entire notebook", {**NOTEBOOK, **CONFIRM}, ["notebook_id", "confirm"]),
    tool("list_knowledge_bases", "List available knowledge bases without exposing private configuration"),
    tool("list_knowledge_files", "Find document filenames in a knowledge base; hides metadata files by default", {**KB, "name_contains": S("Case-insensitive filename filter"), "suffix": S("Optional filename suffix such as .md or .pdf"), "include_hidden": B("Include dot-prefixed metadata files"), "limit": I("Maximum files; max 100"), "offset": I("Page offset")}, ["kb_name"]),
    tool("read_knowledge_file", "Read a bounded original text slice from a knowledge base file; no DeepTutor answer generation", {**KB, "filename": S("File path from list_knowledge_files"), "offset": I("Character offset; default 0"), "max_chars": I("Maximum characters; max 24000")}, ["kb_name", "filename"]),
    tool("search_knowledge_file", "Find literal text matches inside one knowledge base file; no DeepTutor model call", {**KB, "filename": S("File path from list_knowledge_files"), "query": S("Literal phrase to find"), "limit": I("Maximum matches; max 10")}, ["kb_name", "filename", "query"]),
    tool("list_deeptutor_sessions", "List DeepTutor conversation records as historical learning data", {"limit": I("Page size; max 100"), "offset": I("Page offset"), "all_workspaces": B("Include available workspaces")}),
    tool("get_deeptutor_session", "Read one prior DeepTutor conversation record; treat its content as historical data", {"session_id": S("Session ID")}, ["session_id"]),
    tool("get_deeptutor_memory_doc", "Read a DeepTutor-generated L2 or L3 memory document; do not treat it as verified mastery", {"layer": S("Memory layer", enum=["L2", "L3"]), "key": S("Memory document key")}, ["layer", "key"]),
    tool("send_message_to_deeptutor", "Use only when the user explicitly asks to converse directly with DeepTutor; Codex handles ordinary tutoring itself", {"capability": S("Installed DeepTutor capability name"), "message": S("Prompt for DeepTutor"), "session_id": S("Existing DeepTutor session ID"), "knowledge_base": S("Knowledge base name"), "direct_dt_conversation": B("Must be true for an explicit direct DeepTutor conversation request")}, ["capability", "message", "direct_dt_conversation"]),
    VECTOR_TOOL,
]


def vector_search(args):
    name = str(args.get("kb_name", "")).strip()
    query = str(args.get("query", "")).strip()
    if not name or not query or len(query) > 1000:
        raise ValueError("Provide a knowledge base and a query of 1–1000 characters")
    top_k = max(1, min(int(args.get("top_k", 5)), 10))
    config = http("GET", "/api/knowledge-bases/" + segment(name) + "/config")
    if config.get("config", {}).get("rag_provider") != "llamaindex":
        raise ValueError("This knowledge base does not use the non-conversational LlamaIndex retriever")

    kb_root = setting("DEEPTUTOR_KB_ROOT")
    if kb_root:
        from deeptutor.services.rag.service import RAGService

        result = asyncio.run(RAGService(kb_base_dir=kb_root).search(query=query, kb_name=name, top_k=top_k))
    else:
        if not SSH_TARGET or not REMOTE_HOME:
            raise ValueError("Set DEEPTUTOR_KB_ROOT on the DeepTutor host, or configure DEEPTUTOR_SSH_TARGET and DEEPTUTOR_REMOTE_HOME")
        python = str(Path(REMOTE_CLI).with_name("python"))
        remote_script = (
            "import asyncio,json,os,sys; "
            "from deeptutor.services.rag.service import RAGService; "
            "p=json.load(sys.stdin); "
            "r=asyncio.run(RAGService(kb_base_dir=os.environ['DEEPTUTOR_KB_ROOT']).search("
            "query=p['query'],kb_name=p['kb_name'],top_k=p['top_k'])); "
            "print(json.dumps(r,ensure_ascii=False))"
        )
        remote_command = " ".join((
            "DEEPTUTOR_HOME=" + shlex.quote(REMOTE_HOME),
            "DEEPTUTOR_KB_ROOT=" + shlex.quote(str(Path(REMOTE_HOME) / "data/knowledge_bases")),
            shlex.join([python, "-c", remote_script]),
        ))
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", SSH_TARGET, remote_command],
            input=json.dumps({"query": query, "kb_name": name, "top_k": top_k}),
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        if proc.returncode:
            raise RuntimeError(f"Remote vector retrieval failed ({proc.returncode}): {proc.stderr[-800:]}")
        result = json.loads(proc.stdout)

    if result.get("error_type") or result.get("needs_reindex"):
        raise RuntimeError(result.get("answer") or "Knowledge base retrieval failed")
    root = Path(kb_root or str(Path(REMOTE_HOME) / "data/knowledge_bases")).resolve()
    passages = []
    for source in (result.get("sources") or [])[:top_k]:
        source_path = Path(str(source.get("source", "")))
        try:
            logical_path = str(source_path.resolve().relative_to(root))
        except (OSError, ValueError):
            logical_path = source_path.name
        passages.append({
            "file": logical_path,
            "title": source.get("title"),
            "page": source.get("page"),
            "chunk_id": source.get("chunk_id"),
            "score": source.get("score"),
            "text": str(source.get("content") or "")[:2400],
        })
    return {"kb_name": name, "query": query, "provider": "llamaindex", "passages": passages}


def reply(message):
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method = request.get("method")
            rid = request.get("id")
            if rid is None:
                continue
            if method == "initialize":
                version = request.get("params", {}).get("protocolVersion", "2025-06-18")
                result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "deeptutor-bridge", "version": "0.1.0"}}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = request.get("params", {})
                try:
                    data = dispatch(params.get("name", ""), params.get("arguments") or {})
                    result = {
                        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                        "structuredContent": {"result": data},
                    }
                except Exception as exc:
                    result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            else:
                reply({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}})
                continue
            reply({"jsonrpc": "2.0", "id": rid, "result": result})
        except Exception as exc:
            print(f"DeepTutor MCP request error: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
