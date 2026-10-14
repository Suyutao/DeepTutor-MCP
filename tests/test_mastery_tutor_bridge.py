import unittest
from unittest.mock import patch

import deeptutor_mcp


class MasteryTutorBridgeTests(unittest.TestCase):
    def test_tool_catalog_is_exposed(self):
        names = {tool["name"] for tool in deeptutor_mcp.TOOLS}
        self.assertIn("get_mastery_tutor_tools", names)
        self.assertIn("call_mastery_tutor", names)

    def test_catalog_dispatch_reads_native_schemas(self):
        expected = {"tools": [], "instructions": "Follow the built-in tutor"}
        with patch.object(deeptutor_mcp, "http", return_value=expected) as request:
            result = deeptutor_mcp.dispatch("get_mastery_tutor_tools", {})

        self.assertEqual(result, expected)
        request.assert_called_once_with("GET", "/api/mastery-paths/tutor-tools")

    def test_call_dispatch_forwards_native_request_and_client_identity(self):
        args = {
            "path_id": "chemistry path",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "request_id": "request-id-000001",
            "tool": "mastery_assess",
            "arguments": {"knowledge_point_id": "kp1", "passed": True},
            "user_message": "原样学习问题",
            "confirm": True,
        }
        with (
            patch.object(deeptutor_mcp, "TUTOR_CLIENT_ID", "chatgpt"),
            patch.object(deeptutor_mcp, "http", return_value={"success": True}) as request,
        ):
            result = deeptutor_mcp.dispatch("call_mastery_tutor", args)

        self.assertEqual(result, {"success": True})
        request.assert_called_once_with(
            "POST",
            "/api/mastery-paths/topics/chemistry%20path/tutor",
            body={
                "client_id": "chatgpt",
                "session_id": "session-1",
                "turn_id": "turn-1",
                "request_id": "request-id-000001",
                "tool": "mastery_assess",
                "arguments": {"knowledge_point_id": "kp1", "passed": True},
                "user_message": "原样学习问题",
            },
        )

    def test_call_requires_confirmation_and_idempotency_key(self):
        args = {
            "path_id": "chemistry",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "request_id": "short",
            "tool": "record_turn",
        }
        with self.assertRaisesRegex(ValueError, "confirm=true"):
            deeptutor_mcp.dispatch("call_mastery_tutor", args | {"confirm": False})
        with self.assertRaisesRegex(ValueError, "at least 16"):
            deeptutor_mcp.dispatch("call_mastery_tutor", args | {"confirm": True})


if __name__ == "__main__":
    unittest.main()
