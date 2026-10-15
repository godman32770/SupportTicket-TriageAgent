from app.tools import CustomerHistoryTool, KBLookupTool


def test_customer_history_tool():
    tool = CustomerHistoryTool()
    result = tool.fetch("C-100")
    assert result.success is True
    assert "C-100" in result.summary


def test_kb_lookup_tool():
    tool = KBLookupTool()
    result = tool.lookup("mobile_app", "login")
    assert result.success is True
    assert "Password reset" in result.summary or "app" in result.summary.lower()
