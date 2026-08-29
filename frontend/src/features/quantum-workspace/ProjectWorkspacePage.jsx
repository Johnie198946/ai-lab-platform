import { ChevronLeft, FileText, GitBranch, LayoutDashboard, Route } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, useLocation, useParams, useSearchParams } from "react-router-dom";
import { platformApi } from "../../services/platformApi";
import { BusinessIntakePanel } from "./BusinessIntakePanel";
import { AIResourceWorkbench } from "./AIResourceWorkbench";
import { ProjectGraph } from "./ProjectGraph";
import { ProjectSchedule } from "./ProjectSchedule";
import { ProjectDocuments } from "./ProjectDocuments";
import { DashiTaskboardHost } from "./DashiTaskboardHost";
import { StageRail } from "./StageRail";
import { TaskChatDrawer } from "./TaskChatDrawer";
import { BindWorkflowDialog, EditProjectTaskDialog, NewProjectTaskDialog } from "./TaskboardDialogs";

export function ProjectWorkspacePage() {
  const { projectId, viewType } = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [project, setProject] = useState(null);
  const [process, setProcess] = useState(null);
  const [viewData, setViewData] = useState(null);
  const [selectedStageId, setSelectedStageId] = useState(null);
  const [selectedTaskSession, setSelectedTaskSession] = useState(null);
  const [editTask, setEditTask] = useState(null);
  const [workflows, setWorkflows] = useState([]);
  const [workflowState, setWorkflowState] = useState("SYNCING");
  const [boardMode, setBoardMode] = useState("status");
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [bindTask, setBindTask] = useState(null);
  const [dialogBusy, setDialogBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const view = location.pathname.includes("/schedule") ? "schedule" : location.pathname.includes("/documents") ? "documents" : location.pathname.includes("/graph/") ? "graph" : "taskboard";

  const load = useCallback(async () => {
    setError("");
    try {
      const requests = [platformApi.getProject(projectId), platformApi.getProjectProcess(projectId)];
      if (view === "schedule") requests.push(platformApi.getProjectSchedule(projectId));
      if (view === "graph") requests.push(viewType === "ai-resource" ? platformApi.getProjectResourcePlan(projectId) : platformApi.getProjectGraph(projectId, viewType));
      const [projectValue, processValue, selectedView] = await Promise.all(requests);
      setProject(projectValue);
      setProcess(processValue);
      setViewData(selectedView ?? null);
      if (view === "taskboard") {
        setWorkflowState("SYNCING");
        try {
          const workflowValue = await platformApi.listWorkflows();
          setWorkflows(workflowValue.workflows || workflowValue || []);
          setWorkflowState("CONNECTED");
        } catch (reason) {
          setWorkflows([]);
          setWorkflowState("UNCONNECTED");
          setError((current) => current || `canonical workflow 读取失败：${reason.message}`);
        }
      }
    } catch (reason) {
      setError(reason.message);
    } finally {
      setLoading(false);
    }
  }, [projectId, view, viewType]);

  useEffect(() => { setLoading(true); load(); }, [load]);
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

  const createTask = async (taskDraft) => {
    setDialogBusy(true);
    setDialogError("");
    try {
      await platformApi.createProjectTask(projectId, {
        expected_revision: process.process_revision,
        ...taskDraft,
      });
      setNewTaskOpen(false);
      await load();
    } catch (reason) {
      setDialogError(reason.status === 409 ? "项目 revision 已变化，请关闭后重试。" : reason.message);
      if (reason.status === 409) await load();
    } finally {
      setDialogBusy(false);
    }
  };

  const bindWorkflow = async (task, workflowId) => {
    setDialogBusy(true);
    setDialogError("");
    try {
      await platformApi.bindProjectTaskWorkflow(projectId, task.id, {
        expected_revision: process.process_revision,
        workflow_id: workflowId,
      });
      setBindTask(null);
      await load();
    } catch (reason) {
      setDialogError(reason.status === 409 ? "该 Workflow 已被绑定，或项目 revision 已变化。" : reason.message);
      if (reason.status === 409) await load();
    } finally {
      setDialogBusy(false);
    }
  };

  const editTaskDetails = async (taskDraft) => {
    setDialogBusy(true);
    setDialogError("");
    try {
      await platformApi.editProjectTask(projectId, editTask.id, { expected_revision: process.process_revision, ...taskDraft });
      setEditTask(null);
      await load();
    } catch (reason) {
      setDialogError(reason.status === 409 ? "项目 revision 已变化，请关闭后重试。" : reason.message);
      if (reason.status === 409) await load();
    } finally { setDialogBusy(false); }
  };

  const createAndBindWorkflow = async (task) => {
    setDialogBusy(true);
    setDialogError("");
    try {
      const created = await platformApi.createWorkflow({
        title: task.title,
        description: task.summary,
        desired_output: (task.deliverables || []).join("、") || "可审阅业务成果",
        clarification_mode: "dynamic",
      });
      const workflow = created.workflow || created;
      await platformApi.bindProjectTaskWorkflow(projectId, task.id, {
        expected_revision: process.process_revision,
        workflow_id: workflow.id,
      });
      setBindTask(null);
      await load();
    } catch (reason) {
      setDialogError(reason.status === 409 ? "项目 revision 已变化，Workflow 已创建但尚未绑定，请重新选择绑定。" : reason.message);
      if (reason.status === 409) await load();
    } finally {
      setDialogBusy(false);
    }
  };

  const recommendResourcePlan = async (constraints) => {
    try {
      const result = await platformApi.recommendProjectResourcePlan(projectId, {
        request_id: `resource-recommend-${crypto.randomUUID()}`,
        expected_revision: viewData.process_revision,
        constraints,
      });
      setViewData(result);
      setProcess((current) => ({ ...current, process_revision: result.process_revision, resource_plan: result.plan }));
      return result;
    } catch (reason) {
      if (reason.status === 409) await load();
      throw new Error(reason.status === 409 ? "项目 revision 已变化，已刷新最新资源方案，请重新生成。" : reason.message);
    }
  };

  const saveResourcePlan = async (plan) => {
    try {
      const result = await platformApi.saveProjectResourcePlan(projectId, {
        expected_revision: viewData.process_revision,
        plan,
      });
      setViewData(result);
      setProcess((current) => ({ ...current, process_revision: result.process_revision, resource_plan: result.plan }));
      return result;
    } catch (reason) {
      if (reason.status === 409) await load();
      throw new Error(reason.status === 409 ? "项目 revision 已变化，已刷新最新资源方案，请重新修改。" : reason.message);
    }
  };

  const generateSimulationDataset = async ({ simulatorId, rowCount, seed }) => {
    try {
      const result = await platformApi.generateProjectSimulationDataset(projectId, simulatorId, {
        expected_revision: viewData.process_revision,
        row_count: rowCount,
        seed,
      });
      setViewData((current) => ({ ...current, process_revision: result.process_revision, plan: result.plan }));
      setProcess((current) => ({ ...current, process_revision: result.process_revision, resource_plan: result.plan }));
      return result;
    } catch (reason) {
      if (reason.status === 409) await load();
      throw new Error(reason.status === 409 ? "项目 revision 已变化，已刷新方案，请重新生成数据。" : reason.message);
    }
  };

  const askResourceContext = ({ contextId, contextTitle, question, resourcePlan }) => platformApi.askProjectResourceContext(projectId, {
    request_id: `resource-chat-${crypto.randomUUID()}`,
    context_id: contextId,
    context_title: contextTitle,
    question,
    resource_plan: resourcePlan,
  });

  if (loading) return <div className="qw-page-state">正在读取项目真源…</div>;
  if (!project || !process) return <div className="qw-page-state error">{error || "项目不可用"}<Link to="/home">返回 Home</Link></div>;
  return (
    <div className="qw-project-page">
      <div className="qw-project-header">
        <div className="qw-project-title"><Link to="/home" aria-label="返回 Home"><ChevronLeft size={18} /></Link><div><span className="qw-eyebrow">Project · {project.id.slice(-8)}</span><h1>{project.name}</h1><p>{project.goal}</p></div></div>
        <div className="qw-revision"><span>process revision</span><strong>{process.process_revision}</strong></div>
      </div>
      <div className="qw-project-sticky">
        <div className="qw-view-tabs">
          <NavLink to={`/projects/${projectId}/taskboard`}><LayoutDashboard size={15} />Taskboard</NavLink>
          <NavLink to={`/projects/${projectId}/graph/workflow`}><GitBranch size={15} />Workflow</NavLink>
          <NavLink to={`/projects/${projectId}/documents`}><FileText size={15} />Documents</NavLink>
          <NavLink to={`/projects/${projectId}/graph/ai-resource`}><Route size={15} />AI Resource</NavLink>
        </div>
        <StageRail process={process} selectedStageId={selectedStageId} onSelect={setSelectedStageId} />
      </div>
      {error && <p className="qw-error page">{error}</p>}
      {view === "taskboard" && <DashiTaskboardHost project={project} onOpenTaskChat={setSelectedTaskSession} />}
      {view === "schedule" && viewData && <ProjectSchedule schedule={viewData} focusTaskId={searchParams.get("focus_task_id")} />}
      {view === "documents" && <ProjectDocuments projectId={projectId} onRevisionChange={(revision) => setProcess((current) => ({ ...current, process_revision: revision }))} />}
      {view === "graph" && viewType === "workflow" && viewData && <ProjectGraph graph={viewData} process={process} onEditTask={setEditTask} onCreateTask={() => setNewTaskOpen(true)} />}
      {view === "graph" && viewType === "ai-resource" && viewData && <AIResourceWorkbench resourceData={viewData} onRecommend={recommendResourcePlan} onSave={saveResourcePlan} onGenerateDataset={generateSimulationDataset} onAskContext={askResourceContext} />}
      {selectedTaskSession && <TaskChatDrawer project={project} process={process} task={selectedTaskSession.task} cardContext={selectedTaskSession.cardContext} refreshCardContext={selectedTaskSession.refreshCardContext} onClose={() => setSelectedTaskSession(null)} />}
      {editTask && <EditProjectTaskDialog task={editTask} stages={process.stages || []} busy={dialogBusy} error={dialogError} onClose={() => setEditTask(null)} onSubmit={editTaskDetails} />}
      {newTaskOpen && <NewProjectTaskDialog stages={process.stages || []} busy={dialogBusy} error={dialogError} onClose={() => setNewTaskOpen(false)} onSubmit={createTask} />}
      {bindTask && <BindWorkflowDialog task={bindTask} workflows={workflows} busy={dialogBusy} error={dialogError} onClose={() => setBindTask(null)} onBind={bindWorkflow} onCreateAndBind={createAndBindWorkflow} />}
    </div>
  );
}
