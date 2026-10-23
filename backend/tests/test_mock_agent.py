"""Mock agent tests: rule-based NLU must execute real operations and report honestly."""
from datetime import datetime, timedelta

from app.agents import mock_agent
from app.db import get_conn
from app.services import tasks as svc


def _actions_by_tool(result):
    return {a["tool"]: a for a in result["actions"]}


def test_multi_task_creation_from_one_message(clean_db):
    result = mock_agent.run_mock_agent(
        "add finish investor deck by friday 5pm and review PR #142 tomorrow 10am and buy groceries today"
    )
    created = [a for a in result["actions"] if a["tool"] == "create_task" and a["ok"]]
    assert len(created) == 3, f"expected 3 create actions, got {created}"
    tasks = svc.list_tasks()
    titles = [t["title"].lower() for t in tasks]
    assert any("investor deck" in t for t in titles)
    assert any("pr #142" in t for t in titles)
    assert any("groceries" in t for t in titles)
    deck = next(t for t in tasks if "investor deck" in t["title"].lower())
    assert deck["deadline"] is not None
    # Auto-schedule after creation
    assert any(a["tool"] == "generate_schedule" for a in result["actions"])


def test_complete_task_by_title(clean_db):
    t = svc.create_task("Write launch blog", "medium")
    result = mock_agent.run_mock_agent("I finished write launch blog")
    done = [a for a in result["actions"] if a["tool"] == "complete_task" and a["ok"]]
    assert done
    assert svc.get_task(t["id"])["status"] == "done"


def test_delete_task_by_title(clean_db):
    t = svc.create_task("Cancel me", "low")
    result = mock_agent.run_mock_agent("delete cancel me")
    assert any(a["tool"] == "delete_task" and a["ok"] for a in result["actions"])
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) n FROM tasks WHERE id=?", (t["id"],)).fetchone()["n"] == 0


def test_reschedule_task(clean_db):
    t = svc.create_task("Old chore", "low", datetime.now() + timedelta(hours=2), 20)
    result = mock_agent.run_mock_agent("reschedule old chore to tomorrow 9am")
    rs = [a for a in result["actions"] if a["tool"] == "reschedule_task" and a["ok"]]
    assert rs, result
    updated = svc.get_task(t["id"])
    assert datetime.fromisoformat(updated["deadline"]).date() >= datetime.now().date()


def test_replan_intent(clean_db):
    svc.create_task("Missed thing", "medium", datetime.now() - timedelta(hours=2), 30)
    result = mock_agent.run_mock_agent("I missed my work, replan my day")
    rp = [a for a in result["actions"] if a["tool"] == "replan_missed" and a["ok"]]
    assert rp
    assert "Replanned 1" in rp[0]["summary"]


def test_progress_intent(clean_db):
    t = svc.create_task("Counted task", "low")
    svc.complete_task(t["id"])
    result = mock_agent.run_mock_agent("how am I doing?")
    gp = [a for a in result["actions"] if a["tool"] == "get_progress" and a["ok"]]
    assert gp
    assert gp[0]["detail"]["progress"]["done"] == 1


def test_unknown_task_reported_honestly(clean_db):
    result = mock_agent.run_mock_agent("complete totally nonexistent thing")
    assert not any(a["tool"] == "complete_task" and a.get("ok") for a in result["actions"])
    assert any("couldn't find" in n.lower() or "couldn't" in n.lower()
               for n in [result["reply"]])


def test_mock_reply_never_claims_ai(clean_db):
    result = mock_agent.run_mock_agent("add hello task today")
    # Router labels mode='mock'; the mock itself must not fake Bedrock claims
    assert "bedrock" not in result["reply"].lower()
