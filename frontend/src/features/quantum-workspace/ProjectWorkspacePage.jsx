import { ChevronLeft, GitBranch, LayoutDashboard, Route, Rows3 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, useLocation, useParams, useSearchParams } from "react-router-dom";
import { platformApi } from "../../services/platformApi";
import { BusinessIntakePanel } from "./BusinessIntakePanel";
import { ProjectGraph } from "./ProjectGraph";
import { ProjectSchedule } from "./ProjectSchedule";
import { ProjectTaskboard } from "./ProjectTaskboard";
import { StageRail } from "./StageRail";
import { TaskChatDrawer } from "./TaskChatDrawer";

export function ProjectWorkspacePage() {
  const { projectId, viewType } = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [project, setProject] = useState(null);
  const [process, setProcess] = useState(null);
  const [viewData, setViewData] = useState(null);
  const [selectedStageId, setSelectedStageId] = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const view = location.pathname.includes("/schedule") ? "schedule" : location.pathname.includes("/graph/") ? "graph" : "taskboard";

  const load = useCallback(async () => {
    setError("");
    try {
      const requests = [platformApi.getProject(projectId), platformApi.getProjectProcess(projectId)];
      if (view === "schedule") requests.push(platformApi.getProjectSchedule(projectId));
      if (view === "graph") requests.push(platformApi.getProjectGraph(projectId, viewType));
      const [projectValue, processValue, selectedView] = await Promise.all(requests);
      setProject(projectValue);
      setProcess(processValue);
      setViewData(selectedView ?? null);
    } catch (reason) {
      setError(reason.message);
    } finally {
      setLoading(false);
    }
  }, [projectId, view, viewType]);

  useEffect(() => { setLoading(true); load(); }, [load]);
  const stage = useMemo(() => process?.stages?.find((item) => item.id === selectedStageId), [process, selectedStageId]);

  const updateStatus = async (taskId, status) => {
    setError("");
    let reason = null;
    if (status === "BLOCKED" || status === "PAUSED") {
      reason = window.prompt("请填写阻塞或暂停原因（必填）")?.trim() || null;
      if (!reason) return;
    }
    try {
      await platformApi.updateProjectTask(projectId, taskId, {
        expected_revision: process.process_revision,
        status,
        reason,
      });
      await load();
    } catch (reason) {
      setError(reason.status === 409 ? "项目已被其他操作更新，已重新读取最新 revision。" : reason.message);
      await load();
    }
  };

  if (loading) return <div className="qw-page-state">正在读取项目真源…</div>;
  if (!project || !process) return <div className="qw-page-state error">{error || "项目不可用"}<Link to="/home">返回 Home</Link></div>;
  return (
    <div className="qw-project-page">
      <div className="qw-project-header">
        <div className="qw-project-title"><Link to="/home" aria-label="返回 Home"><ChevronLeft size={18} /></Link><div><span className="qw-eyebrow">Project · {project.id.slice(-8)}</span><h1>{project.name}</h1><p>{project.goal}</p></div></div>
        <div className="qw-revision"><span>process revision</span><strong>{process.process_revision}</strong></div>
      </div>
      <div className="qw-view-tabs">
        <NavLink to={`/projects/${projectId}/taskboard`}><LayoutDashboard size={15} />Taskboard</NavLink>
        <NavLink to={`/projects/${projectId}/schedule`}><Rows3 size={15} />甘特图</NavLink>
        <NavLink to={`/projects/${projectId}/graph/workflow`}><GitBranch size={15} />Workflow</NavLink>
        <NavLink to={`/projects/${projectId}/graph/ai-resource`}><Route size={15} />AI Resource</NavLink>
      </div>
      <StageRail process={process} selectedStageId={selectedStageId} onSelect={(id) => setSelectedStageId((current) => current === id ? null : id)} />
      {stage && <div className="qw-stage-focus"><strong>{stage.name}</strong><span>{stage.status} · {stage.progress}%</span><button onClick={() => setSelectedStageId(null)}>清除筛选</button></div>}
      {error && <p className="qw-error page">{error}</p>}
      {view === "taskboard" && <ProjectTaskboard process={process} selectedStageId={selectedStageId} onTaskOpen={setSelectedTask} onStatusChange={updateStatus} intake={<BusinessIntakePanel project={project} process={process} onApplied={load} />} />}
      {view === "schedule" && viewData && <ProjectSchedule schedule={viewData} focusTaskId={searchParams.get("focus_task_id")} />}
      {view === "graph" && viewData && <ProjectGraph graph={viewData} />}
      {selectedTask && <TaskChatDrawer project={project} process={process} task={selectedTask} onClose={() => setSelectedTask(null)} />}
    </div>
  );
}
