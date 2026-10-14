# Built-in Mastery tutor over MCP

This adapter exposes DeepTutor's native Mastery tutor workflow through two MCP tools:

- get_mastery_tutor_tools returns the tool schemas and usage instructions published by DeepTutor.
- call_mastery_tutor forwards a selected native tutor tool and its arguments to DeepTutor. Quiz creation, grading, assessment, review state, and turn records are handled by DeepTutor's built-in implementation.

## Upstream requirement

The DeepTutor HTTP endpoints used by this adapter are proposed in [HKUDS/DeepTutor PR #1785](https://github.com/HKUDS/DeepTutor/pull/1785). As of 2026-10-14, that PR is open and waiting for maintainer merge. Install or update DeepTutor to a deployment that contains the patch before using these tools. Until then, the catalog request may return HTTP 404.

The patch adds:

- GET /api/mastery-paths/tutor-tools — native tutor tool schemas and instructions.
- POST /api/mastery-paths/topics/{path_id}/tutor — execute one selected native tool through the same implementation used by DeepTutor's internal tutor.

## Apply the source patch manually

The complete source patch currently proposed by PR #1785 is included at `patches/deeptutor-mastery-tutor-http.patch`. It contains both upstream PR commits, including the test adjustment. The patch was made against DeepTutor commit `f07029cf` (v1.6.13). It is suitable for a source checkout at that exact base; a different base may need a rebase or conflict resolution.

In a clean DeepTutor checkout, create a local branch, check the base, verify applicability, and apply:

~~~sh
git status --short --branch
git rev-parse --short HEAD  # expected: f07029cf
git switch -c local/mastery-tutor-http
git apply --check /path/to/DeepTutor-MCP/patches/deeptutor-mastery-tutor-http.patch
git apply /path/to/DeepTutor-MCP/patches/deeptutor-mastery-tutor-http.patch
~~~

Run the focused test from the DeepTutor checkout using its project environment:

~~~sh
python -m pytest deeptutor/learning/tests/test_external_tutor.py -q
~~~

To undo the patch before making other edits, check and reverse it:

~~~sh
git apply --reverse --check /path/to/DeepTutor-MCP/patches/deeptutor-mastery-tutor-http.patch
git apply --reverse /path/to/DeepTutor-MCP/patches/deeptutor-mastery-tutor-http.patch
~~~

Applying the patch changes source files only. Deploying that checkout and restarting a DeepTutor service are separate steps; the MCP adapter and patch file do not change a running installation.

## Configure the MCP server

Use the existing DeepTutor API connection and authentication settings:

~~~dotenv
DEEPTUTOR_BASE_URL=http://127.0.0.1:8001
DEEPTUTOR_MCP_TUTOR_CLIENT_ID=chatgpt
~~~

DEEPTUTOR_MCP_TUTOR_CLIENT_ID is a stable, non-secret identifier for this MCP client. Give each separately configured AI client a distinct value. DeepTutor authentication still uses DEEPTUTOR_TOKEN or DEEPTUTOR_TOKEN_FILE; keep bearer credentials in a private environment file.

For stdio, pass these variables to the MCP process. For Streamable HTTP, add them to the service environment and restart the MCP service. Then rescan the MCP tools in the client. No additional service port or DeepTutor credential is introduced by this adapter.

## Tutor call sequence

1. Call get_mastery_tutor_tools before a Mastery tutoring session. Follow the returned native schemas and instructions.
2. Use list_mastery_paths to select the learner's existing path_id.
3. For each tutor operation, call call_mastery_tutor with the selected native tool name and matching arguments. Set confirm: true only when the user has asked to use this Mastery tutor workflow.
4. Keep session_id stable for the tutoring session. Reuse the same turn_id for tool calls belonging to one learner turn. Use a distinct request_id of at least 16 characters for each operation; reuse that same ID if retrying the same request.
5. On the first operation of a learner turn, include the learner's message verbatim in user_message. After composing the response, save the complete tutor reply with tool: record_turn and assistant_message.

The adapter sends these operations through DeepTutor's existing tutor tools. It does not infer a learner declaration or let an external model directly set a mastery value.
