"""WorkerManager 编排原语测试：parallel 和 pipeline。"""

import json

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext


def build_agent(tmp_path, outputs):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient(outputs),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
    )


# ---------------------------------------------------------------------------
# parallel() 测试
# ---------------------------------------------------------------------------


class TestParallel:
    def test_parallel_runs_all_tasks_and_returns_structured_results(self, tmp_path):
        # 保护目标：parallel 能并行执行多个 worker 并返回每个的结构化结果
        # 场景：3 个 Explore worker 各自完成不同任务
        agent = build_agent(tmp_path, [
            "<final>task A done</final>",
            "<final>task B done</final>",
            "<final>task C done</final>",
        ])

        results = agent.worker_manager.parallel([
            {"description": "Task A", "prompt": "do A", "subagent_type": "Explore"},
            {"description": "Task B", "prompt": "do B", "subagent_type": "Explore"},
            {"description": "Task C", "prompt": "do C", "subagent_type": "Explore"},
        ])

        assert len(results) == 3
        assert all(r["status"] == "completed" for r in results)
        assert results[0]["description"] == "Task A"
        assert results[1]["description"] == "Task B"
        assert results[2]["description"] == "Task C"

    def test_parallel_returns_result_content(self, tmp_path):
        # 保护目标：每个 worker 的 result 字段包含实际输出
        agent = build_agent(tmp_path, [
            "<final>alpha</final>",
            "<final>beta</final>",
        ])

        results = agent.worker_manager.parallel([
            {"description": "First", "prompt": "do first", "subagent_type": "Explore"},
            {"description": "Second", "prompt": "do second", "subagent_type": "Explore"},
        ])

        results_by_desc = {r["description"]: r["result"] for r in results}
        assert "alpha" in results_by_desc["First"]
        assert "beta" in results_by_desc["Second"]

    def test_parallel_records_duration(self, tmp_path):
        # 保护目标：每个 worker 记录执行时间
        agent = build_agent(tmp_path, [
            "<final>done</final>",
            "<final>done</final>",
        ])

        results = agent.worker_manager.parallel([
            {"description": "A", "prompt": "go", "subagent_type": "Explore"},
            {"description": "B", "prompt": "go", "subagent_type": "Explore"},
        ])

        for r in results:
            assert "duration_ms" in r
            assert isinstance(r["duration_ms"], (int, float))

    def test_parallel_with_single_task(self, tmp_path):
        # 保护目标：单任务 parallel 等价于 spawn
        agent = build_agent(tmp_path, ["<final>solo done</final>"])

        results = agent.worker_manager.parallel([
            {"description": "Solo", "prompt": "do it", "subagent_type": "Explore"},
        ])

        assert len(results) == 1
        assert results[0]["status"] == "completed"
        assert "solo done" in results[0]["result"]

    def test_parallel_empty_tasks(self, tmp_path):
        # 保护目标：空任务列表返回空结果
        agent = build_agent(tmp_path, [])

        results = agent.worker_manager.parallel([])

        assert results == []


# ---------------------------------------------------------------------------
# pipeline() 测试
# ---------------------------------------------------------------------------


class TestPipeline:
    def test_pipeline_runs_stages_sequentially(self, tmp_path):
        # 保护目标：pipeline 按顺序执行每个 stage
        agent = build_agent(tmp_path, [
            "<final>stage 0 output</final>",
            "<final>stage 1 output</final>",
        ])

        results = agent.worker_manager.pipeline([
            {"description": "Stage 0", "prompt_template": "do step 0", "subagent_type": "Explore"},
            {"description": "Stage 1", "prompt_template": "continue with {input}", "subagent_type": "Explore"},
        ])

        assert len(results) == 2
        assert results[0]["stage_index"] == 0
        assert results[1]["stage_index"] == 1
        assert all(r["status"] == "completed" for r in results)

    def test_pipeline_passes_output_to_next_stage(self, tmp_path):
        # 保护目标：前一个 stage 的输出通过 {input} 传给下一个 stage
        agent = build_agent(tmp_path, [
            "<final>hello from stage 0</final>",
            "<final>processed: hello from stage 0</final>",
        ])

        results = agent.worker_manager.pipeline([
            {"description": "Producer", "prompt_template": "produce output", "subagent_type": "Explore"},
            {"description": "Consumer", "prompt_template": "process: {input}", "subagent_type": "Explore"},
        ])

        assert "hello from stage 0" in results[0]["result"]
        assert "processed" in results[1]["result"]

    def test_pipeline_with_initial_input(self, tmp_path):
        # 保护目标：initial_input 传给第一个 stage
        agent = build_agent(tmp_path, [
            "<final>got initial input</final>",
        ])

        results = agent.worker_manager.pipeline(
            [{"description": "First", "prompt_template": "handle: {input}", "subagent_type": "Explore"}],
            initial_input="seed data",
        )

        assert len(results) == 1
        assert results[0]["status"] == "completed"

    def test_pipeline_failure_stops_subsequent_stages(self, tmp_path):
        # 保护目标：某个 stage 失败后，后续 stage 被标记为 skipped
        # FakeModelClient 在没有更多输出时会出错
        agent = build_agent(tmp_path, [
            "<final>stage 0 ok</final>",
            # stage 1 没有对应输出，会触发异常或空响应
        ])

        results = agent.worker_manager.pipeline([
            {"description": "Stage 0", "prompt_template": "do step 0", "subagent_type": "Explore"},
            {"description": "Stage 1", "prompt_template": "do step 1", "subagent_type": "Explore"},
            {"description": "Stage 2", "prompt_template": "do step 2", "subagent_type": "Explore"},
        ])

        # Stage 0 应完成
        assert results[0]["status"] == "completed"
        # 至少有一个后续 stage 被跳过或失败
        later_statuses = [r["status"] for r in results[1:]]
        assert any(s in ("skipped", "failed", "stopped") for s in later_statuses)

    def test_pipeline_empty_stages(self, tmp_path):
        # 保护目标：空 stages 返回空结果
        agent = build_agent(tmp_path, [])

        results = agent.worker_manager.pipeline([])

        assert results == []

    def test_pipeline_records_stage_index(self, tmp_path):
        # 保护目标：每个结果包含 stage_index
        agent = build_agent(tmp_path, [
            "<final>a</final>",
            "<final>b</final>",
            "<final>c</final>",
        ])

        results = agent.worker_manager.pipeline([
            {"description": "S0", "prompt_template": "go", "subagent_type": "Explore"},
            {"description": "S1", "prompt_template": "go", "subagent_type": "Explore"},
            {"description": "S2", "prompt_template": "go", "subagent_type": "Explore"},
        ])

        assert results[0]["stage_index"] == 0
        assert results[1]["stage_index"] == 1
        assert results[2]["stage_index"] == 2


# ---------------------------------------------------------------------------
# 编排集成测试
# ---------------------------------------------------------------------------


class TestOrchestrationIntegration:
    def test_parallel_then_pipeline_mixed(self, tmp_path):
        # 保护目标：parallel 和 pipeline 可以在同一 agent 上交替使用
        agent = build_agent(tmp_path, [
            "<final>parallel A</final>",
            "<final>parallel B</final>",
            "<final>pipeline step</final>",
        ])

        # 先 parallel
        par_results = agent.worker_manager.parallel([
            {"description": "A", "prompt": "do A", "subagent_type": "Explore"},
            {"description": "B", "prompt": "do B", "subagent_type": "Explore"},
        ])
        assert len(par_results) == 2

        # 再 pipeline
        pipe_results = agent.worker_manager.pipeline([
            {"description": "Step", "prompt_template": "do step", "subagent_type": "Explore"},
        ])
        assert len(pipe_results) == 1

    def test_parallel_drains_notifications(self, tmp_path):
        # 保护目标：parallel 执行后通知队列有内容
        agent = build_agent(tmp_path, [
            "<final>done A</final>",
            "<final>done B</final>",
        ])

        agent.worker_manager.parallel([
            {"description": "A", "prompt": "go", "subagent_type": "Explore"},
            {"description": "B", "prompt": "go", "subagent_type": "Explore"},
        ])

        notifications = agent.worker_manager.drain_notifications()
        assert len(notifications) >= 2


# ---------------------------------------------------------------------------
# DAG 编排测试
# ---------------------------------------------------------------------------


class TestDAG:
    def test_dag_runs_independent_tasks_in_parallel(self, tmp_path):
        # 保护目标：无依赖的任务并行执行
        agent = build_agent(tmp_path, [
            "<final>A done</final>",
            "<final>B done</final>",
            "<final>C done</final>",
        ])

        result = agent.worker_manager.dag([
            {"id": "a", "description": "Task A", "prompt": "do A", "subagent_type": "Explore"},
            {"id": "b", "description": "Task B", "prompt": "do B", "subagent_type": "Explore"},
            {"id": "c", "description": "Task C", "prompt": "do C", "subagent_type": "Explore"},
        ])

        assert len(result["results"]) == 3
        assert all(r["status"] == "completed" for r in result["results"])
        assert len(result["failed"]) == 0

    def test_dag_respects_dependencies(self, tmp_path):
        # 保护目标：依赖关系被正确执行，B 在 A 完成后才运行
        agent = build_agent(tmp_path, [
            "<final>from A</final>",
            "<final>B got: from A</final>",
        ])

        result = agent.worker_manager.dag([
            {"id": "a", "description": "Producer", "prompt": "produce data", "subagent_type": "Explore"},
            {"id": "b", "description": "Consumer", "prompt": "process {deps:a}", "subagent_type": "Explore", "depends_on": ["a"]},
        ])

        assert len(result["results"]) == 2
        assert result["results"][0]["id"] == "a"
        assert result["results"][0]["status"] == "completed"
        assert result["results"][1]["id"] == "b"
        assert result["results"][1]["status"] == "completed"

    def test_dag_failure_blocks_dependents(self, tmp_path):
        # 保护目标：上游失败时，下游被标记为 skipped
        # A 成功 → B 失败（无输出） → C 被跳过（依赖 B）
        agent = build_agent(tmp_path, [
            "<final>from A</final>",
            # B 没有输出，会失败
        ])

        result = agent.worker_manager.dag([
            {"id": "a", "description": "A", "prompt": "do A", "subagent_type": "Explore"},
            {"id": "b", "description": "B", "prompt": "do B", "subagent_type": "Explore", "depends_on": ["a"]},
            {"id": "c", "description": "C", "prompt": "do C", "subagent_type": "Explore", "depends_on": ["b"]},
        ])

        results_by_id = {r["id"]: r for r in result["results"]}
        # A 完成
        assert results_by_id["a"]["status"] == "completed"
        # B 失败（依赖 A，A 完成后 B 执行但无输出）
        assert results_by_id["b"]["status"] != "completed"
        # C 被跳过（依赖 B，B 失败）
        assert results_by_id["c"]["status"] == "skipped"
        assert "b" in result["failed"]

    def test_dag_diamond_dependency(self, tmp_path):
        # 保护目标：菱形依赖 A→B, A→C, B+C→D
        agent = build_agent(tmp_path, [
            "<final>root</final>",
            "<final>left</final>",
            "<final>right</final>",
            "<final>merged</final>",
        ])

        result = agent.worker_manager.dag([
            {"id": "a", "description": "Root", "prompt": "root", "subagent_type": "Explore"},
            {"id": "b", "description": "Left", "prompt": "left", "subagent_type": "Explore", "depends_on": ["a"]},
            {"id": "c", "description": "Right", "prompt": "right", "subagent_type": "Explore", "depends_on": ["a"]},
            {"id": "d", "description": "Merge", "prompt": "merge", "subagent_type": "Explore", "depends_on": ["b", "c"]},
        ])

        assert len(result["results"]) == 4
        assert all(r["status"] == "completed" for r in result["results"])
        # D 应该在 B 和 C 之后
        order = result["execution_order"]
        assert order.index("d") > order.index("b")
        assert order.index("d") > order.index("c")

    def test_dag_empty_tasks(self, tmp_path):
        # 保护目标：空任务返回空结果
        agent = build_agent(tmp_path, [])

        result = agent.worker_manager.dag([])

        assert result["results"] == []
        assert result["execution_order"] == []
        assert result["failed"] == []


# ---------------------------------------------------------------------------
# 消息队列测试
# ---------------------------------------------------------------------------


class TestMessageQueue:
    def test_post_and_read_messages(self, tmp_path):
        # 保护目标：消息能正确发布和读取
        agent = build_agent(tmp_path, [])

        agent.worker_manager.post_message("channel1", "hello")
        agent.worker_manager.post_message("channel1", "world")

        messages = agent.worker_manager.read_messages("channel1")
        assert len(messages) == 2
        assert messages[0]["content"] == "hello"
        assert messages[1]["content"] == "world"

    def test_read_messages_with_since(self, tmp_path):
        # 保护目标：since 参数能跳过旧消息
        agent = build_agent(tmp_path, [])

        agent.worker_manager.post_message("ch", "msg0")
        agent.worker_manager.post_message("ch", "msg1")
        agent.worker_manager.post_message("ch", "msg2")

        messages = agent.worker_manager.read_messages("ch", since=1)
        assert len(messages) == 2
        assert messages[0]["content"] == "msg1"

    def test_clear_messages(self, tmp_path):
        # 保护目标：clear 能清空指定通道
        agent = build_agent(tmp_path, [])

        agent.worker_manager.post_message("ch1", "a")
        agent.worker_manager.post_message("ch2", "b")
        agent.worker_manager.clear_messages("ch1")

        assert agent.worker_manager.read_messages("ch1") == []
        assert len(agent.worker_manager.read_messages("ch2")) == 1

    def test_clear_all_messages(self, tmp_path):
        # 保护目标：不指定通道时清空全部
        agent = build_agent(tmp_path, [])

        agent.worker_manager.post_message("ch1", "a")
        agent.worker_manager.post_message("ch2", "b")
        agent.worker_manager.clear_messages()

        assert agent.worker_manager.read_messages("ch1") == []
        assert agent.worker_manager.read_messages("ch2") == []

    def test_read_empty_channel(self, tmp_path):
        # 保护目标：读取不存在的通道返回空列表
        agent = build_agent(tmp_path, [])

        assert agent.worker_manager.read_messages("nonexistent") == []
