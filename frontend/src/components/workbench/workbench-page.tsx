"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Bot,
  FileCode2,
  FileText,
  FolderTree,
  History,
  Loader2,
  PanelRightOpen,
  RotateCcw,
  Save,
  Settings2,
  Sparkles,
} from "lucide-react";
import { Toaster, toast } from "sonner";

import { Button } from "@/components/ui/button";
import { MemoryApprovalCard } from "@/components/chat/memory-approval-card";
import { Input } from "@/components/ui/input";
import { defaultModelSettings, loadModelSettings, saveModelSettings, shouldPersistModelSettings, type ModelSettings } from "@/lib/model-settings";
import {
  getFile,
  listAgents,
  approveMemoryProposal,
  listMemoryProposals,
  rejectMemoryProposal,
  getEvalJob,
  getGraphSummary,
  getTrace,
  listTraces,
  runEval,
  runGraphDemo,
  saveFile,
  type GraphSummary,
  type AgentProfile,
  type EvalJobResponse,
  type MemoryProposal,
  type TraceDetail,
  type TraceSummary,
} from "@/lib/api";

const MonacoEditor = dynamic(() => import("@/components/monaco-markdown-editor").then((module) => module.MonacoMarkdownEditor), {
  ssr: false,
});

type ToolView = "workspace" | "memory" | "skills" | "personas" | "examples";
type MainTab = "files" | "traces" | "settings";
type InspectorGroup = "workspace" | "memory" | "skills" | "personas";
type TraceStatus = "idle" | "loading" | "ready" | "error";
type LayoutSizeKey = "sidebarWidth" | "contentWidth" | "inspectorListWidth" | "tracesListWidth";
type LayoutSizes = Record<LayoutSizeKey, number>;

type InspectorFile = {
  label: string;
  path: string;
  group: InspectorGroup;
};

const toolViews: Array<{ id: ToolView; label: string; icon: typeof FolderTree }> = [
  { id: "workspace", label: "Workspace", icon: FolderTree },
  { id: "memory", label: "Memory", icon: History },
  { id: "skills", label: "Skills", icon: Sparkles },
  { id: "personas", label: "Agent Personas", icon: Bot },
  { id: "examples", label: "Examples", icon: FileText },
];

const mainTabs: Array<{ id: MainTab; label: string; icon: typeof FolderTree }> = [
  { id: "files", label: "Files", icon: FolderTree },
  { id: "traces", label: "Traces", icon: History },
  { id: "settings", label: "Settings", icon: Settings2 },
];

const memoryProjectionFiles: InspectorFile[] = [
  { label: "Shared / USER.md", path: "backend/memory/approved_memory/USER.md", group: "memory" },
  { label: "Shared / PROJECT.md", path: "backend/memory/approved_memory/PROJECT.md", group: "memory" },
  { label: "灯塔 / AGENT.md", path: "backend/memory/approved_memory/agents/lighthouse/AGENT.md", group: "memory" },
  { label: "灯塔 / RELATIONSHIP.md", path: "backend/memory/approved_memory/agents/lighthouse/RELATIONSHIP.md", group: "memory" },
  { label: "火花 / AGENT.md", path: "backend/memory/approved_memory/agents/spark/AGENT.md", group: "memory" },
  { label: "火花 / RELATIONSHIP.md", path: "backend/memory/approved_memory/agents/spark/RELATIONSHIP.md", group: "memory" },
  { label: "砥石 / AGENT.md", path: "backend/memory/approved_memory/agents/whetstone/AGENT.md", group: "memory" },
  { label: "砥石 / RELATIONSHIP.md", path: "backend/memory/approved_memory/agents/whetstone/RELATIONSHIP.md", group: "memory" },
];

const inspectorFiles: InspectorFile[] = [
  { label: "MEMORY.md (template)", path: "backend/memory/MEMORY.md", group: "memory" },
  ...memoryProjectionFiles,
  { label: "SOUL.md", path: "backend/workspace/SOUL.md", group: "workspace" },
  { label: "IDENTITY.md", path: "backend/workspace/IDENTITY.md", group: "workspace" },
  { label: "USER.md", path: "backend/workspace/USER.md", group: "workspace" },
  { label: "AGENTS.md", path: "backend/workspace/AGENTS.md", group: "workspace" },
  { label: "SKILLS_SNAPSHOT.md", path: "backend/workspace/SKILLS_SNAPSHOT.md", group: "workspace" },
  { label: "INTERVIEW_DEMO.md", path: "backend/workspace/INTERVIEW_DEMO.md", group: "workspace" },
  { label: "灯塔 / lighthouse.md", path: "backend/agents/personas/lighthouse.md", group: "personas" },
  { label: "火花 / spark.md", path: "backend/agents/personas/spark.md", group: "personas" },
  { label: "砥石 / whetstone.md", path: "backend/agents/personas/whetstone.md", group: "personas" },
  { label: "get_weather / SKILL.md", path: "backend/skills/get_weather/SKILL.md", group: "skills" },
  { label: "interview_answer_builder / SKILL.md", path: "backend/skills/interview_answer_builder/SKILL.md", group: "skills" },
  { label: "resume_story_coach / SKILL.md", path: "backend/skills/resume_story_coach/SKILL.md", group: "skills" },
];

const interviewDemoPrompts = [
  "Summarize Mini-OpenClaw as a resume-ready AI agent project in 4 bullets.",
  "Explain why the project uses transparent file-based memory instead of only hidden vector memory.",
  "Pretend you are an interviewer. Ask me 5 hard follow-up questions about Mini-OpenClaw's evals, traces, and failure handling.",
  "Turn this project into a 90-second interview answer that sounds practical instead of hype-driven.",
  "Compare the engineering value of evals, observability, and user isolation in this project.",
  "Rewrite Mini-OpenClaw into a STAR story about improving an AI agent from prototype to credible engineering project.",
] as const;

const graphRagDemoPrompt =
  "Use search_knowledge_base with use_graph=true to connect Mini-OpenClaw's eval notes, interview demo pack, skills, and runtime diagnostics. Explain what the graph-expanded evidence adds beyond direct matches, and keep the answer honest: this is graph-assisted retrieval, not full community-summarization GraphRAG.";

const LAYOUT_SIZES_STORAGE_KEY = "mini-openclaw-layout-sizes";
const defaultLayoutSizes: LayoutSizes = {
  sidebarWidth: 320,
  contentWidth: 1120,
  inspectorListWidth: 250,
  tracesListWidth: 260,
};

function formatTimestamp(value: string): string {
  if (!value) {
    return "No activity yet";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function getInspectorGroupLabel(group: InspectorGroup): string {
  if (group === "workspace") {
    return "Workspace";
  }

  if (group === "memory") {
    return "Memory";
  }

  if (group === "personas") {
    return "Agent Personas";
  }

  return "Skills";
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function coerceLayoutSizes(raw: unknown): LayoutSizes {
  if (!raw || typeof raw !== "object") {
    return defaultLayoutSizes;
  }

  const candidate = raw as Partial<Record<LayoutSizeKey, unknown>>;

  return {
    sidebarWidth: typeof candidate.sidebarWidth === "number" ? candidate.sidebarWidth : defaultLayoutSizes.sidebarWidth,
    contentWidth: typeof candidate.contentWidth === "number" ? candidate.contentWidth : defaultLayoutSizes.contentWidth,
    inspectorListWidth: typeof candidate.inspectorListWidth === "number" ? candidate.inspectorListWidth : defaultLayoutSizes.inspectorListWidth,
    tracesListWidth: typeof candidate.tracesListWidth === "number" ? candidate.tracesListWidth : defaultLayoutSizes.tracesListWidth,
  };
}

export function WorkbenchPage() {
  const [activeView, setActiveView] = useState<ToolView>("workspace");
  const [activeTab, setActiveTab] = useState<MainTab>("files");
  const [layoutSizes, setLayoutSizes] = useState<LayoutSizes>(defaultLayoutSizes);
  const [traceSummaries, setTraceSummaries] = useState<TraceSummary[]>([]);
  const [traceDetails, setTraceDetails] = useState<Record<string, TraceDetail>>({});
  const [traceStatus, setTraceStatus] = useState<TraceStatus>("idle");
  const [activeTraceId, setActiveTraceId] = useState<string>("");
  const [graphSummary, setGraphSummary] = useState<GraphSummary | null>(null);
  const [isGraphAvailable, setIsGraphAvailable] = useState(false);
  const [graphStatus, setGraphStatus] = useState<TraceStatus>("idle");
  const [selectedInspectorPath, setSelectedInspectorPath] = useState<string>(inspectorFiles[0]?.path ?? "");
  const [editorValue, setEditorValue] = useState("");
  const [loadedEditorValue, setLoadedEditorValue] = useState("");
  const [loadedFilePath, setLoadedFilePath] = useState("");
  const [isInspectorLoading, setIsInspectorLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [inspectorError, setInspectorError] = useState<string | null>(null);
  const [modelSettings, setModelSettings] = useState<ModelSettings>(defaultModelSettings);
  const [isModelSettingsHydrated, setIsModelSettingsHydrated] = useState(false);
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);
  const [selectedPersonaId, setSelectedPersonaId] = useState<"lighthouse" | "spark" | "whetstone">("lighthouse");
  const [pendingMemoryProposals, setPendingMemoryProposals] = useState<MemoryProposal[]>([]);
  const [isMemoryReviewOpen, setIsMemoryReviewOpen] = useState(false);
  const [isReviewingMemoryProposal, setIsReviewingMemoryProposal] = useState(false);
  const [settingsSavedAt, setSettingsSavedAt] = useState<string | null>(null);
  const [isRunningGraphDemo, setIsRunningGraphDemo] = useState(false);
  const [isRunningEval, setIsRunningEval] = useState(false);
  const [activeEvalJobId, setActiveEvalJobId] = useState<string | null>(null);
  const [evalJob, setEvalJob] = useState<EvalJobResponse | null>(null);
  const [activeResizeKey, setActiveResizeKey] = useState<LayoutSizeKey | null>(null);
  const dragStateRef = useRef<{
    key: LayoutSizeKey;
    min: number;
    max: number;
    direction: 1 | -1;
    startPointer: number;
    startSize: number;
  } | null>(null);

  async function refreshTraces(preferredTraceId?: string) {
    try {
      setTraceStatus("loading");
      const items = await listTraces();
      setTraceSummaries(items);
      setActiveTraceId((current) => preferredTraceId || current || items[0]?.trace_id || "");
      setTraceStatus("ready");
    } catch {
      setTraceSummaries([]);
      setTraceStatus("error");
    }
  }

  async function refreshGraphSummary() {
    try {
      setGraphStatus("loading");
      const payload = await getGraphSummary();
      setIsGraphAvailable(payload.available);
      setGraphSummary(payload.summary);
      setGraphStatus("ready");
    } catch {
      setIsGraphAvailable(false);
      setGraphSummary(null);
      setGraphStatus("error");
    }
  }

  async function refreshPendingMemoryProposals() {
    try {
      setPendingMemoryProposals(await listMemoryProposals("pending"));
    } catch {
      setPendingMemoryProposals([]);
    }
  }

  async function handleMemoryProposalDecision(decision: "approve" | "reject") {
    const proposal = pendingMemoryProposals[0];
    if (!proposal || isReviewingMemoryProposal) {
      return;
    }

    setIsReviewingMemoryProposal(true);
    try {
      if (decision === "approve") {
        await approveMemoryProposal(proposal.proposal_id);
      } else {
        await rejectMemoryProposal(proposal.proposal_id);
      }
      const remaining = await listMemoryProposals("pending");
      setPendingMemoryProposals(remaining);
      setIsMemoryReviewOpen(remaining.length > 0);
      toast.success(decision === "approve" ? "Memory approved" : "Memory rejected");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Memory review failed";
      toast.error("Memory review failed", { description: message });
    } finally {
      setIsReviewingMemoryProposal(false);
    }
  }

  useEffect(() => {
    if (typeof window === "undefined" || !shouldPersistModelSettings(isModelSettingsHydrated)) {
      return;
    }

    setModelSettings(loadModelSettings());
    setIsModelSettingsHydrated(true);
  }, []);

  useEffect(() => {
    void listAgents().then(setAgentProfiles).catch(() => setAgentProfiles([]));
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || !shouldPersistModelSettings(isModelSettingsHydrated)) {
      return;
    }

    const raw = window.localStorage.getItem(LAYOUT_SIZES_STORAGE_KEY);
    if (!raw) {
      return;
    }

    try {
      setLayoutSizes(coerceLayoutSizes(JSON.parse(raw)));
    } catch {
      window.localStorage.removeItem(LAYOUT_SIZES_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    saveModelSettings(modelSettings);
    setSettingsSavedAt(new Date().toLocaleTimeString());
  }, [isModelSettingsHydrated, modelSettings]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    window.localStorage.setItem(LAYOUT_SIZES_STORAGE_KEY, JSON.stringify(layoutSizes));
  }, [layoutSizes]);

  useEffect(() => {
    function handlePointerMove(event: PointerEvent) {
      const dragState = dragStateRef.current;
      if (!dragState) {
        return;
      }

      const delta = event.clientX - dragState.startPointer;
      const nextSize = clamp(dragState.startSize + (delta * dragState.direction), dragState.min, dragState.max);
      setLayoutSizes((current) => ({
        ...current,
        [dragState.key]: nextSize,
      }));
    }

    function stopDragging() {
      if (!dragStateRef.current) {
        return;
      }
      dragStateRef.current = null;
      setActiveResizeKey(null);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopDragging);
    window.addEventListener("pointercancel", stopDragging);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopDragging);
      window.removeEventListener("pointercancel", stopDragging);
    };
  }, []);

  useEffect(() => {
    if (!selectedInspectorPath) {
      return;
    }

    let mounted = true;
    setIsInspectorLoading(true);
    setInspectorError(null);

    void getFile(selectedInspectorPath)
      .then((payload) => {
        if (!mounted) {
          return;
        }

        setEditorValue(payload.content);
        setLoadedEditorValue(payload.content);
        setLoadedFilePath(payload.path);
      })
      .catch((error) => {
        if (!mounted) {
          return;
        }

        const message = error instanceof Error ? error.message : "Failed to load file";
        setInspectorError(message);
        toast.error("Failed to load file", { description: message });
      })
      .finally(() => {
        if (mounted) {
          setIsInspectorLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [selectedInspectorPath]);

  useEffect(() => {
    if (activeView === "memory") {
      setSelectedInspectorPath("backend/memory/approved_memory/USER.md");
      setActiveTab("files");
      return;
    }

    if (activeView === "skills") {
      setSelectedInspectorPath("backend/skills/get_weather/SKILL.md");
      setActiveTab("files");
      return;
    }

    if (activeView === "personas") {
      setSelectedInspectorPath(`backend/agents/personas/${selectedPersonaId}.md`);
      setActiveTab("files");
      return;
    }

    if (activeView === "workspace") {
      setSelectedInspectorPath((current) => current || inspectorFiles[0]?.path || "");
      setActiveTab("files");
      return;
    }

    setActiveTab("traces");
  }, [activeView]);

  useEffect(() => {
    void refreshTraces();
    void refreshGraphSummary();
    void refreshPendingMemoryProposals();
  }, []);

  useEffect(() => {
    if (!activeTraceId || traceDetails[activeTraceId]) {
      return;
    }

    let mounted = true;
    setTraceStatus("loading");

    void getTrace(activeTraceId)
      .then((detail) => {
        if (!mounted) {
          return;
        }

        setTraceDetails((current) => ({
          ...current,
          [activeTraceId]: detail,
        }));
        setTraceStatus("ready");
      })
      .catch(() => {
        if (!mounted) {
          return;
        }

        setTraceStatus("error");
      });

    return () => {
      mounted = false;
    };
  }, [activeTraceId, traceDetails]);

  useEffect(() => {
    if (traceSummaries.length === 0) {
      return;
    }

    setActiveTraceId((current) => {
      if (current && traceSummaries.some((trace) => trace.trace_id === current)) {
        return current;
      }
      return traceSummaries[0]?.trace_id ?? current;
    });
  }, [traceSummaries]);

  useEffect(() => {
    if (!activeEvalJobId) {
      return;
    }

    const jobId = activeEvalJobId;
    let mounted = true;
    let timer: number | null = null;

    async function pollEvalJob() {
      try {
        const job = await getEvalJob(jobId);
        if (!mounted) {
          return;
        }

        setEvalJob(job);
        if (job.status === "completed") {
          setIsRunningEval(false);
          toast.success("Eval finished", {
            description: job.result ? `Saved ${job.result.output}` : "Report is ready.",
          });
          return;
        }

        if (job.status === "failed") {
          setIsRunningEval(false);
          toast.error("Eval failed", { description: job.error ?? "Unknown eval error" });
          return;
        }

        timer = window.setTimeout(pollEvalJob, 1500);
      } catch (error) {
        if (!mounted) {
          return;
        }
        const message = error instanceof Error ? error.message : "Failed to read eval job status";
        setIsRunningEval(false);
        toast.error("Eval status failed", { description: message });
      }
    }

    setIsRunningEval(true);
    void pollEvalJob();

    return () => {
      mounted = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [activeEvalJobId]);

  const selectedInspectorFile = inspectorFiles.find((item) => item.path === selectedInspectorPath) ?? null;
  const selectedInspectorLabel = selectedInspectorFile?.label ?? selectedInspectorPath;
  const isGeneratedMemoryProjection = selectedInspectorPath.includes("/approved_memory/");
  const isDirty = loadedFilePath === selectedInspectorPath && editorValue !== loadedEditorValue;
  const visibleInspectorGroups = useMemo<InspectorGroup[]>(() => {
    if (activeView === "memory") {
      return ["memory"];
    }

    if (activeView === "skills") {
      return ["skills"];
    }

    if (activeView === "personas") {
      return ["personas"];
    }

    return ["workspace", "memory", "skills", "personas"];
  }, [activeView]);
  const groupedInspectorFiles = useMemo(
    () =>
      visibleInspectorGroups.map((group) => ({
        group,
        files: inspectorFiles.filter((file) => file.group === group),
      })),
    [visibleInspectorGroups],
  );
  const inspectorDescription =
    activeView === "memory"
      ? "Review and update the long-term memory files here."
      : activeView === "skills"
        ? "Inspect the local skill definitions without mixing them into the main chat flow."
        : activeView === "personas"
          ? "Versioned persona prompts are active-agent sources, separate from shared constraints and approved private memory."
        : "Inspect and edit workspace prompts, memory files, and local skills from one place.";
  const selectedInspectorGroup = selectedInspectorFile?.group ?? "workspace";
  const activeTrace = activeTraceId ? traceDetails[activeTraceId] ?? null : null;
  const displayedExpandedEvidenceCount = activeTrace?.graph_retrieval?.evidence_chain?.filter((item) => item.origin === "expanded").length ?? 0;
  const routePayload = activeTrace?.events.find((event) => event.kind === "agent_routed")?.payload;
  const handoffPayload = activeTrace?.events.find((event) => event.kind === "handoff_requested")?.payload;
  const bootstrapRecords = activeTrace?.events
    .filter((event) => event.kind === "memory_loaded")
    .flatMap((event) => Array.isArray(event.payload.records) ? event.payload.records.filter((record): record is Record<string, unknown> => Boolean(record) && typeof record === "object") : []) ?? [];
  const isInspectorCompact = layoutSizes.contentWidth < 860;
  const isTracesCompact = layoutSizes.contentWidth < 900;

  function beginHorizontalResize(
    key: LayoutSizeKey,
    {
      min,
      oppositeMin,
      direction,
    }: {
      min: number;
      oppositeMin: number;
      direction: 1 | -1;
    },
  ) {
    return (event: React.PointerEvent<HTMLDivElement>) => {
      const parentWidth = event.currentTarget.parentElement?.getBoundingClientRect().width ?? window.innerWidth;
      const max = Math.max(min, parentWidth - oppositeMin - 24);
      dragStateRef.current = {
        key,
        min,
        max,
        direction,
        startPointer: event.clientX,
        startSize: layoutSizes[key],
      };
      setActiveResizeKey(key);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      event.preventDefault();
    };
  }

  async function handleRunGraphDemo() {
    if (isRunningGraphDemo) {
      return;
    }

    setIsRunningGraphDemo(true);
    try {
      const result = await runGraphDemo(graphRagDemoPrompt, `workbench-demo-${Date.now()}`);
      toast.success("Graph demo finished", { description: "Trace details are available in the Traces tab." });
      await refreshTraces(result.trace_id);
      setActiveView("examples");
      setActiveTab("traces");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Graph demo failed";
      toast.error("Graph demo failed", { description: message });
    } finally {
      setIsRunningGraphDemo(false);
    }
  }

  async function handleRunEval() {
    if (isRunningEval) {
      return;
    }

    setIsRunningEval(true);
    try {
      const job = await runEval();
      setEvalJob(job);
      setActiveEvalJobId(job.job_id);
      toast.success("Eval queued", {
        description: `Job ${job.job_id} is running in the background.`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Eval failed";
      const hint =
        /not found|404/i.test(message) && !/runEval failed/i.test(message)
          ? "The backend likely needs a restart so it can load /api/evals/run."
          : message;
      toast.error("Eval failed", { description: hint });
      setIsRunningEval(false);
    }
  }

  async function handleSaveInspector() {
    if (!selectedInspectorPath || isSaving || isGeneratedMemoryProjection) {
      if (isGeneratedMemoryProjection) {
        toast.info("Memory projections are read-only", {
          description: "Approve or reject a memory proposal to update this projection.",
        });
      }
      return;
    }

    setIsSaving(true);
    setInspectorError(null);

    try {
      const payload = await saveFile(selectedInspectorPath, editorValue);
      setEditorValue(payload.content);
      setLoadedEditorValue(payload.content);
      setLoadedFilePath(payload.path);
      toast.success("Saved file", { description: payload.path });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to save file";
      setInspectorError(message);
      toast.error("Failed to save file", { description: message });
    } finally {
      setIsSaving(false);
    }
  }

  function handleModelSettingChange(field: keyof ModelSettings, value: string) {
    setModelSettings((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function handleResetModelSettings() {
    setModelSettings(defaultModelSettings);
    toast.success("Restored default model settings");
  }

  function handleUseBackendDefaultKey() {
    setModelSettings((current) => ({
      ...current,
      apiKey: "",
    }));
    toast.success("Cleared local API key", {
      description: "The next request will use the backend default key.",
    });
  }

  function handleSaveModelSettings() {
    if (typeof window === "undefined") {
      return;
    }

    saveModelSettings(modelSettings);
    const timestamp = new Date().toLocaleTimeString();
    setSettingsSavedAt(timestamp);
    toast.success("Saved model settings", {
      description: "Stored locally in this browser.",
    });
  }

  return (
    <>
      <Toaster position="top-right" richColors />
      <main className="min-h-screen px-4 py-4 text-foreground sm:px-5 sm:py-5">
        <div className="mx-auto flex w-full max-w-[1800px] flex-col gap-4">
          <header className="rounded-[24px] border border-[#ead9c5] bg-[#fffaf4]/90 px-5 py-5 shadow-[0_16px_40px_rgba(90,59,46,0.10)] backdrop-blur sm:px-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="max-w-3xl">
                <div className="inline-flex items-center gap-2 rounded-full border border-[#e7c4ad] bg-[#fff1e6] px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-[#a34f32]">
                  <Sparkles className="h-3.5 w-3.5" />
                  Workbench
                </div>
                <h1 className="mt-3 text-2xl font-semibold tracking-tight text-[#34231d] sm:text-3xl">Memory Harbor 的观察台，只在需要证据时打开。</h1>
                <p className="mt-2 text-sm leading-6 text-stone-600 sm:text-base">
                  这里保留记忆文件、运行 trace、图检索与评测；主对话仍专注于人与三位 Agent 的协作。
                </p>
              </div>
              <Link href="/">
                <Button className="h-11 rounded-2xl border-[#ddc3ac] bg-white px-4 text-[#5a3b2e] hover:bg-[#fff1e6]" type="button" variant="outline">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Back to Chat
                </Button>
              </Link>
            </div>
          </header>

          <section className="flex min-h-[calc(100vh-2rem)] flex-col gap-4 xl:flex-row xl:items-start">
            <aside
              className="flex min-h-0 shrink-0 flex-col overflow-y-auto rounded-[22px] border border-[#5a3b2e] bg-[linear-gradient(180deg,#5a3b2e,#432a20)] p-5 shadow-[0_18px_50px_rgba(90,59,46,0.22)] xl:sticky xl:top-4 xl:max-h-[calc(100vh-2.5rem)]"
              style={{ width: `min(100%, ${layoutSizes.sidebarWidth}px)` }}
            >
              <div className="border-b border-white/10 pb-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-sky-300/70">Tools</p>
                <h2 className="mt-3 text-2xl font-semibold tracking-tight text-white">Advanced controls only</h2>
                <p className="mt-2 text-sm leading-6 text-slate-300">This page no longer doubles as a chat surface. Use it to edit files, inspect traces, and manage runtime settings.</p>
              </div>

              <nav className="mt-4 grid grid-cols-2 gap-2 xl:grid-cols-1" aria-label="Workbench views">
                {toolViews.map((item) => {
                  const Icon = item.icon;
                  const active = item.id === activeView;

                  return (
                    <button
                      key={item.id}
                      className={[
                        "flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-3 text-center text-sm transition-all duration-150 xl:justify-start xl:px-4 xl:text-left",
                        active
                          ? "border-sky-400/30 bg-sky-400/12 font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
                          : "border-transparent bg-transparent text-slate-300 hover:border-white/10 hover:bg-white/5 hover:text-white",
                      ].join(" ")}
                      onClick={() => setActiveView(item.id)}
                      type="button"
                    >
                      <Icon className={["h-4 w-4", active ? "text-sky-300" : "text-slate-500"].join(" ")} />
                      {item.label}
                    </button>
                  );
                })}
              </nav>

              <div className="mt-5 rounded-[18px] border border-white/10 bg-white/5 p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">Quick actions</p>
                <div className="mt-3 space-y-2">
                  <Button className="h-10 w-full justify-start rounded-xl" onClick={() => { setActiveView("memory"); setSelectedInspectorPath("backend/memory/MEMORY.md"); setActiveTab("files"); }} type="button" variant="outline">
                    <FileText className="mr-2 h-4 w-4" />
                    Open MEMORY.md
                  </Button>
                  <Button className="h-10 w-full justify-start rounded-xl" onClick={() => { setActiveView("workspace"); setSelectedInspectorPath("backend/workspace/INTERVIEW_DEMO.md"); setActiveTab("files"); }} type="button" variant="outline">
                    <FileText className="mr-2 h-4 w-4" />
                    Open demo sheet
                  </Button>
                  <Button className="h-10 w-full justify-start rounded-xl border-slate-200 bg-white text-slate-700 hover:bg-slate-50" disabled={isRunningEval} onClick={handleRunEval} type="button" variant="outline">
                    {isRunningEval ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileCode2 className="mr-2 h-4 w-4" />}
                    Run Eval
                  </Button>
                  <Button className="h-10 w-full justify-start rounded-xl bg-[#c96f4a] text-white hover:bg-[#ad5938]" disabled={isRunningGraphDemo} onClick={handleRunGraphDemo} type="button">
                    {isRunningGraphDemo ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <History className="mr-2 h-4 w-4" />}
                    Run Graph RAG trace
                  </Button>
                </div>
                {evalJob ? (
                  <div
                    className={[
                      "mt-4 rounded-[16px] border p-3 text-xs leading-5",
                      evalJob.status === "failed"
                        ? "border-rose-200 bg-rose-50/80 text-rose-950"
                        : evalJob.status === "completed"
                          ? "border-emerald-200 bg-emerald-50/80 text-emerald-950"
                          : "border-sky-200 bg-sky-50/80 text-sky-950",
                    ].join(" ")}
                  >
                    <p className="font-semibold uppercase tracking-[0.2em]">Eval job</p>
                    <p className="mt-2 text-sm font-medium">Status: {evalJob.status}</p>
                    <p className="mt-1 break-all">Job: {evalJob.job_id}</p>
                    {evalJob.result ? (
                      <>
                        <p className="mt-2 text-sm font-medium">Dataset: {evalJob.result.dataset_size} tasks</p>
                        <p className="mt-1 break-all">Report: {evalJob.result.output}</p>
                        <p className="mt-1 break-all">Markdown: {evalJob.result.markdown_output}</p>
                        <p className="mt-1">Profiles: {evalJob.result.profiles.join(", ")}</p>
                      </>
                    ) : null}
                    {evalJob.error ? (
                      <p className="mt-2 break-words font-medium">Error: {evalJob.error}</p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </aside>

            <div
              aria-hidden="true"
              className="relative hidden w-4 shrink-0 cursor-col-resize touch-none items-center justify-center xl:flex"
              onPointerDown={beginHorizontalResize("sidebarWidth", { min: 260, oppositeMin: 860, direction: 1 })}
            >
              <span className="h-24 w-px rounded-full bg-slate-300" />
              <span className="absolute inset-y-6 left-1/2 w-[3px] -translate-x-1/2 rounded-full bg-slate-200/90" />
            </div>

            <section
              className="flex min-h-[72vh] min-w-0 flex-col rounded-[22px] border border-[#ead9c5] bg-[#f8eee1]/75 p-4 shadow-[0_12px_34px_rgba(90,59,46,0.07)] sm:p-5"
              style={{ width: `min(100%, ${layoutSizes.contentWidth}px)` }}
            >
              <div className="flex items-start justify-between gap-4 border-b border-[#ead9c5] pb-5">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#a77760]">Evidence Surface</p>
                  <h2 className="mt-3 text-2xl font-semibold tracking-tight text-[#34231d]">一次只看一类证据</h2>
                  <p className="mt-2 text-sm leading-6 text-stone-500">
                    在文件、trace 和设置之间切换，不把诊断信息塞回主对话。
                  </p>
                </div>
                <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-500">
                  <span
                    className={[
                      "h-2 w-2 rounded-full",
                      traceStatus === "error" ? "bg-rose-500" : traceStatus === "loading" ? "bg-amber-500" : "bg-emerald-500",
                    ].join(" ")}
                  />
                  {traceSummaries.length} traces · {inspectorFiles.length} files
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2">
                {mainTabs.map((tab) => {
                  const Icon = tab.icon;
                  const active = tab.id === activeTab;
                  return (
                    <button
                      key={tab.id}
                      className={[
                        "rounded-xl border px-3 py-2.5 text-sm font-medium transition",
                        active ? "border-slate-900 bg-slate-950 text-white" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
                      ].join(" ")}
                      onClick={() => setActiveTab(tab.id)}
                      type="button"
                    >
                      <span className="inline-flex items-center gap-2">
                        <Icon className="h-4 w-4" />
                        {tab.label}
                      </span>
                    </button>
                  );
                })}
              </div>

              {activeView === "examples" ? (
                <section className="mt-5 rounded-[18px] border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Examples</p>
                      <h3 className="mt-2 text-base font-semibold text-slate-950">Demo files and Graph RAG checks</h3>
                      <p className="mt-1 text-sm leading-6 text-slate-500">Examples stay here as optional diagnostics and storytelling material, not in the main chat flow. To trigger Graph RAG, click the blue button here or the quick action on the left, then open the Traces tab to inspect the generated run.</p>
                    </div>
                    <Button className="h-9 rounded-xl px-3" onClick={() => { setSelectedInspectorPath("backend/workspace/INTERVIEW_DEMO.md"); setActiveTab("files"); }} type="button" variant="outline">
                      <FileText className="mr-2 h-4 w-4" />
                      Open sheet
                    </Button>
                  </div>
                  <div className="mt-4 rounded-2xl border border-sky-200 bg-[linear-gradient(135deg,#ecfeff,#f8fafc)] p-4 shadow-sm">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-sky-600">Graph RAG spotlight</p>
                        <h4 className="mt-2 text-sm font-semibold text-slate-950">Graph-assisted retrieval demo</h4>
                        <p className="mt-1 text-sm leading-6 text-slate-600">
                          Run a dedicated graph retrieval check and review the resulting trace details in the Traces tab.
                        </p>
                      </div>
                      <Button className="h-10 shrink-0 rounded-xl bg-sky-600 px-4 text-white hover:bg-sky-700" disabled={isRunningGraphDemo} onClick={handleRunGraphDemo} type="button">
                        {isRunningGraphDemo ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <History className="mr-2 h-4 w-4" />}
                        Run Graph RAG trace
                      </Button>
                    </div>
                    <div className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-3">
                      <div className="rounded-xl border border-white/80 bg-white/70 px-3 py-2">
                        <p className="font-semibold text-slate-500">Index</p>
                        <p className="mt-1 text-slate-900">{graphStatus === "loading" ? "Loading" : isGraphAvailable ? "Available" : "Missing"}</p>
                      </div>
                      <div className="rounded-xl border border-white/80 bg-white/70 px-3 py-2">
                        <p className="font-semibold text-slate-500">Nodes</p>
                        <p className="mt-1 text-slate-900">{graphSummary?.node_count ?? 0}</p>
                      </div>
                      <div className="rounded-xl border border-white/80 bg-white/70 px-3 py-2">
                        <p className="font-semibold text-slate-500">Edges</p>
                        <p className="mt-1 text-slate-900">{graphSummary?.edge_count ?? 0}</p>
                      </div>
                    </div>
                    {(graphSummary?.preview_nodes?.length || graphSummary?.preview_edges?.length) ? (
                      <div className="mt-4 grid gap-3 lg:grid-cols-2">
                        <div className="rounded-xl border border-sky-200 bg-white/75 p-3">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-700">真实节点样本</p>
                          <div className="mt-2 space-y-2">
                            {graphSummary?.preview_nodes?.map((node) => (
                              <div className="rounded-lg border border-sky-100 bg-white px-2.5 py-2" key={node.id}>
                                <p className="text-xs font-semibold text-slate-800">{node.label}</p>
                                <p className="mt-0.5 break-words text-[11px] text-slate-500">{node.type}{node.path ? ` · ${node.path}` : ""}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                        <div className="rounded-xl border border-sky-200 bg-white/75 p-3">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-700">真实连边样本</p>
                          <div className="mt-2 space-y-2">
                            {graphSummary?.preview_edges?.map((edge) => (
                              <div className="rounded-lg border border-sky-100 bg-white px-2.5 py-2 text-[11px] text-slate-600" key={edge.id}>
                                <p className="break-words font-medium text-slate-800">{edge.source.label} <span className="text-sky-700">--{edge.type}--&gt;</span> {edge.target.label}</p>
                                <p className="mt-0.5 text-slate-500">{edge.source.type} → {edge.target.type}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                  <div className="mt-4 grid gap-2">
                    {interviewDemoPrompts.map((prompt) => (
                      <div key={prompt} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
                        {prompt}
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}

              {activeView === "personas" ? (
                <section className="mt-5 rounded-[18px] border border-[#e6c9b2] bg-[#fffaf4] p-4 shadow-sm">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#a77760]">Agent Personas</p>
                  <h3 className="mt-2 text-base font-semibold text-[#34231d]">人格来源与记忆边界</h3>
                  <p className="mt-1 text-sm leading-6 text-stone-600">人格来自版本化 Markdown，并只在当前运行 Agent 的 Prompt 中加载。共享 SOUL.md / IDENTITY.md 是基础约束；批准后的私有记忆位于 <code>approved_memory/agents/&#123;agent_id&#125;/</code>，不属于人格。</p>
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    {agentProfiles.map((profile) => {
                      const selected = profile.agent_id === selectedPersonaId;
                      return (
                        <button
                          key={profile.agent_id}
                          className={["rounded-2xl border p-4 text-left transition", selected ? "border-[#c96f4a] bg-[#fff1e6] shadow-sm" : "border-[#ead9c5] bg-white hover:border-[#d9b89d]"].join(" ")}
                          onClick={() => {
                            setSelectedPersonaId(profile.agent_id);
                            setSelectedInspectorPath(profile.persona_path ?? `backend/agents/personas/${profile.agent_id}.md`);
                          }}
                          type="button"
                        >
                          <p className="font-semibold text-[#5a3b2e]">{profile.display_name} <span className="text-xs font-medium text-stone-400">{profile.english_name}</span></p>
                          <p className="mt-2 text-xs leading-5 text-stone-600">职责：{profile.community_role}</p>
                          <p className="mt-1 text-xs leading-5 text-stone-500">认知重点：{profile.cognitive_focus}</p>
                          <p className="mt-2 text-[11px] text-stone-400">可 handoff 至：{profile.allowed_handoff_targets.length ? profile.allowed_handoff_targets.join("、") : "无"}</p>
                        </button>
                      );
                    })}
                  </div>
                  {agentProfiles.length === 0 ? <p className="mt-3 text-sm text-rose-700">Agent profile metadata is unavailable; the persona files can still be inspected below.</p> : null}
                </section>
              ) : null}

              {activeView === "memory" ? (
                <section className="mt-5 rounded-[18px] border border-emerald-200 bg-emerald-50/70 p-4 shadow-sm">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-700">Memory projections</p>
                  <h3 className="mt-2 text-base font-semibold text-emerald-950">按 Agent 查看已批准记忆</h3>
                  <p className="mt-1 text-sm leading-6 text-emerald-900/75">共享记忆对所有 Agent 可见；私有记忆只会在对应 Agent 的新 Session Bootstrap 中注入。投影文件由审批结果生成，因此只读。</p>
                  <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                    {[
                      { label: "共享记忆", detail: "USER.md · PROJECT.md", path: "backend/memory/approved_memory/USER.md" },
                      { label: "灯塔", detail: "只看灯塔私有投影", path: "backend/memory/approved_memory/agents/lighthouse/RELATIONSHIP.md" },
                      { label: "火花", detail: "只看火花私有投影", path: "backend/memory/approved_memory/agents/spark/RELATIONSHIP.md" },
                      { label: "砥石", detail: "只看砥石私有投影", path: "backend/memory/approved_memory/agents/whetstone/RELATIONSHIP.md" },
                    ].map((projection) => (
                      <button
                        key={projection.label}
                        className={[
                          "rounded-xl border px-3 py-3 text-left transition",
                          selectedInspectorPath === projection.path
                            ? "border-emerald-700 bg-emerald-700 text-white shadow-sm"
                            : "border-emerald-200 bg-white/80 text-emerald-950 hover:border-emerald-400 hover:bg-white",
                        ].join(" ")}
                        onClick={() => setSelectedInspectorPath(projection.path)}
                        type="button"
                      >
                        <p className="text-sm font-semibold">{projection.label}</p>
                        <p className={["mt-1 text-xs", selectedInspectorPath === projection.path ? "text-white/75" : "text-emerald-800/75"].join(" ")}>{projection.detail}</p>
                      </button>
                    ))}
                  </div>
                  <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/80 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-amber-950">待审批记忆</p>
                        <p className="mt-1 text-xs leading-5 text-amber-900/75">
                          {pendingMemoryProposals.length > 0
                            ? `${pendingMemoryProposals.length} 条提案尚未进入长期记忆。`
                            : "当前没有待审批提案。"}
                        </p>
                      </div>
                      {pendingMemoryProposals.length > 0 ? (
                        <Button className="rounded-xl bg-amber-600 text-white hover:bg-amber-700" onClick={() => setIsMemoryReviewOpen(true)} type="button">
                          Review {pendingMemoryProposals.length}
                        </Button>
                      ) : null}
                    </div>
                    {pendingMemoryProposals[0] ? <p className="mt-3 line-clamp-2 text-xs leading-5 text-amber-950">下一条：{pendingMemoryProposals[0].content}</p> : null}
                  </div>
                </section>
              ) : null}

              {activeTab === "files" ? (
                <section className="mt-5 flex min-h-[760px] flex-col overflow-hidden rounded-[18px] border border-slate-200 bg-white shadow-sm">
                  <div className="border-b border-slate-200 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Files</p>
                        <p className="mt-1 text-sm text-slate-500">{inspectorDescription}</p>
                      </div>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        {visibleInspectorGroups.map((group) => (
                          <span
                            key={group}
                            className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500"
                          >
                            {getInspectorGroupLabel(group)}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className={["flex min-h-[660px] flex-1 gap-4 overflow-hidden p-4", isInspectorCompact ? "flex-col" : "flex-row"].join(" ")}>
                    <div
                      className={[
                        "flex shrink-0 flex-col rounded-[18px] border border-slate-200 bg-white p-3 shadow-sm",
                        isInspectorCompact ? "min-h-[260px] max-h-[320px] w-full" : "min-h-[660px] w-full max-w-[360px]",
                      ].join(" ")}
                      style={{ width: isInspectorCompact ? "100%" : `${layoutSizes.inspectorListWidth}px` }}
                    >
                      <div className="flex items-center justify-between gap-2 px-2 pb-3">
                        <div className="flex items-center gap-2">
                          <FolderTree className="h-4 w-4 text-slate-400" />
                          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Files</p>
                        </div>
                        <PanelRightOpen className="h-4 w-4 text-slate-300" />
                      </div>
                      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
                        {groupedInspectorFiles.map(({ group, files }) => (
                          <div key={group} className="space-y-1.5">
                            <p className="px-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">{getInspectorGroupLabel(group)}</p>
                            <div className="space-y-1">
                              {files.map((file) => {
                                const active = file.path === selectedInspectorPath;

                                return (
                                  <button
                                    key={file.path}
                                    className={[
                                      "flex w-full items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition",
                                      active
                                        ? "border-slate-900 bg-slate-950 text-white shadow-[0_10px_25px_rgba(15,23,42,0.18)]"
                                        : "border-transparent bg-slate-50/80 text-slate-700 hover:border-slate-200 hover:bg-slate-100",
                                    ].join(" ")}
                                    onClick={() => setSelectedInspectorPath(file.path)}
                                    type="button"
                                  >
                                    <FileText className={["mt-0.5 h-4 w-4 shrink-0", active ? "text-white/80" : "text-slate-400"].join(" ")} />
                                    <div className="min-w-0 flex-1">
                                      <p className="truncate text-sm font-medium">{file.label}</p>
                                      <p className={["mt-1 truncate text-[11px]", active ? "text-white/60" : "text-slate-400"].join(" ")}>
                                        {file.path}
                                      </p>
                                    </div>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {!isInspectorCompact ? (
                      <div
                        aria-hidden="true"
                        className="relative hidden w-4 shrink-0 cursor-col-resize touch-none items-center justify-center lg:flex"
                        onPointerDown={beginHorizontalResize("inspectorListWidth", { min: 180, oppositeMin: 360, direction: 1 })}
                      >
                        <span className="h-20 w-px rounded-full bg-slate-300" />
                        <span className="absolute inset-y-6 left-1/2 w-[3px] -translate-x-1/2 rounded-full bg-slate-200/90" />
                      </div>
                    ) : null}

                    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-[18px] border border-slate-200 bg-white shadow-sm">
                      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <FileCode2 className="h-4 w-4 text-primary" />
                            <p className="truncate text-sm font-semibold text-slate-900">{selectedInspectorLabel}</p>
                            <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                              {getInspectorGroupLabel(selectedInspectorGroup)}
                            </span>
                            {isDirty ? (
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-700">
                                Unsaved
                              </span>
                            ) : null}
                          </div>
                          <p className="mt-1 truncate text-xs text-slate-500">{selectedInspectorPath}</p>
                        </div>
                        <Button className="h-10 rounded-xl px-4 sm:shrink-0" disabled={isInspectorLoading || isSaving || isGeneratedMemoryProjection} onClick={handleSaveInspector} type="button">
                          {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                          {isGeneratedMemoryProjection ? "Generated" : "Save"}
                        </Button>
                      </div>

                      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
                        {isInspectorLoading ? (
                          <div className="flex h-full items-center justify-center gap-3 text-sm text-slate-500">
                            <Loader2 className="h-4 w-4 animate-spin text-primary" />
                            Loading file...
                          </div>
                        ) : (
                          <div className="h-full min-h-0 min-w-0 overflow-hidden">
                            <MonacoEditor height="100%" onChange={setEditorValue} onSave={handleSaveInspector} readOnly={isGeneratedMemoryProjection} value={editorValue} />
                          </div>
                        )}
                      </div>

                      <div className="border-t border-slate-200 px-4 py-3">
                        <p className="text-sm text-slate-600">
                          {isGeneratedMemoryProjection ? "Generated from approved proposals. Use memory review to change it." : isSaving ? "Saving changes..." : inspectorError ? `Save error: ${inspectorError}` : "Cmd/Ctrl+S saves the current file."}
                        </p>
                      </div>
                    </div>
                  </div>
                </section>
              ) : null}

              {activeTab === "traces" ? (
                <section className="mt-5 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[18px] border border-slate-200 bg-white shadow-sm">
                  <div className="border-b border-slate-200 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Traces</p>
                        <p className="mt-1 text-sm text-slate-500">Inspect runs, tool calls, failures, graph retrieval metadata, and latency from one place.</p>
                      </div>
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                        {traceSummaries.length} runs
                      </span>
                    </div>
                  </div>

                  <div className={["flex min-h-0 flex-1 gap-4 overflow-hidden p-4", isTracesCompact ? "flex-col" : "flex-row"].join(" ")}>
                    <div
                      className={[
                        "flex shrink-0 flex-col rounded-[18px] border border-slate-200 bg-white p-3 shadow-sm",
                        isTracesCompact ? "min-h-[220px] max-h-[240px] w-full" : "min-h-[220px] w-full max-w-[340px]",
                      ].join(" ")}
                      style={{ width: isTracesCompact ? "100%" : `${layoutSizes.tracesListWidth}px` }}
                    >
                      <div className="flex items-center justify-between gap-2 px-2 pb-3">
                        <div className="flex items-center gap-2">
                          <History className="h-4 w-4 text-slate-400" />
                          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Runs</p>
                        </div>
                        <PanelRightOpen className="h-4 w-4 text-slate-300" />
                      </div>
                      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
                        {traceSummaries.length === 0 ? (
                          <div className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">No traces yet.</div>
                        ) : (
                          traceSummaries.map((trace) => {
                            const active = trace.trace_id === activeTraceId;
                            return (
                              <button
                                key={trace.trace_id}
                                className={[
                                  "w-full rounded-xl border px-3 py-2.5 text-left transition",
                                  active ? "border-slate-900 bg-slate-950 text-white" : "border-transparent bg-slate-50 text-slate-700 hover:border-slate-200 hover:bg-slate-100",
                                ].join(" ")}
                                onClick={() => setActiveTraceId(trace.trace_id)}
                                type="button"
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <span className="truncate text-sm font-medium">{trace.trace_id}</span>
                                  <span className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{trace.final_status}</span>
                                </div>
                                <p className={["mt-1 text-xs", active ? "text-white/65" : "text-slate-500"].join(" ")}>{trace.session_id}</p>
                                <p className={["mt-1 text-xs", active ? "text-white/50" : "text-slate-400"].join(" ")}>{trace.latency_ms ?? 0} ms · {trace.active_agent_id ?? "legacy agent"}{trace.handoff_count > 0 ? ` · ${trace.handoff_count} handoff` : ""}</p>
                              </button>
                            );
                          })
                        )}
                      </div>
                    </div>

                    {!isTracesCompact ? (
                      <div
                        aria-hidden="true"
                        className="relative hidden w-4 shrink-0 cursor-col-resize touch-none items-center justify-center lg:flex"
                        onPointerDown={beginHorizontalResize("tracesListWidth", { min: 180, oppositeMin: 420, direction: 1 })}
                      >
                        <span className="h-20 w-px rounded-full bg-slate-300" />
                        <span className="absolute inset-y-6 left-1/2 w-[3px] -translate-x-1/2 rounded-full bg-slate-200/90" />
                      </div>
                    ) : null}

                    <div className="flex min-h-0 min-w-0 flex-1 flex-col rounded-[18px] border border-slate-200 bg-white shadow-sm">
                      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <FileCode2 className="h-4 w-4 text-primary" />
                            <p className="truncate text-sm font-semibold text-slate-900">{activeTrace?.trace_id ?? activeTraceId ?? "Select a trace"}</p>
                            <span className={["rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em]", activeTrace?.final_status === "error" ? "border-rose-200 bg-rose-50 text-rose-700" : activeTrace?.final_status === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-500"].join(" ")}>
                              {activeTrace?.final_status ?? traceStatus}
                            </span>
                          </div>
                          <p className="mt-1 truncate text-xs text-slate-500">{activeTrace?.session_id ?? "No trace selected"}</p>
                        </div>
                      </div>
                      <div className="min-h-0 flex-1 overflow-y-auto p-4">
                        {activeTrace ? (
                          <div className="space-y-3">
                            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                              <p>Model: {activeTrace.model_name}</p>
                              <p className="mt-1">Agent: {activeTrace.active_agent_id ?? "legacy agent"} · Route: {activeTrace.route_reason ?? "legacy"}</p>
                              {activeTrace.handoff_count > 0 ? <p className="mt-1">Handoffs: {activeTrace.handoff_count}</p> : null}
                              <p className="mt-1">Latency: {activeTrace.latency_ms ?? 0} ms</p>
                              <p className="mt-1">Started: {formatTimestamp(activeTrace.start_time)}</p>
                              {activeTrace.error_category ? <p className="mt-1">Error category: {activeTrace.error_category}</p> : null}
                              {activeTrace.retry_count > 0 ? <p className="mt-1">Retries: {activeTrace.retry_count}</p> : null}
                              {activeTrace.friendly_message ? <p className="mt-2 text-rose-700">{activeTrace.friendly_message}</p> : null}
                            </div>
                            {routePayload ? (
                              <div className="rounded-2xl border border-[#e6c9b2] bg-[#fffaf4] p-4 text-sm text-stone-700">
                                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#a77760]">路由与上下文</p>
                                <p className="mt-2">路由方式：{String(routePayload.route_reason ?? "历史记录未保存该字段")}</p>
                                <p className="mt-1">当前 Agent：{String(routePayload.display_name ?? routePayload.agent_id ?? "历史记录未保存该字段")}</p>
                                {handoffPayload ? (
                                  <>
                                    <p className="mt-2 font-medium">交接：{String(handoffPayload.from_agent_id ?? "?")} → {String(handoffPayload.to_agent_id ?? "?")}</p>
                                    <p className="mt-1">任务：{String(handoffPayload.task ?? "历史记录未保存该字段")}</p>
                                    <p className="mt-1">原因：{String(handoffPayload.reason ?? "历史记录未保存该字段")}</p>
                                    <p className="mt-1 font-mono text-xs text-stone-500">{String(handoffPayload.handoff_id ?? "历史记录未保存该字段")}</p>
                                    <p className="mt-1">共享证据：{String(handoffPayload.evidence_count ?? "历史记录未保存该字段")} 条</p>
                                    {Array.isArray(handoffPayload.evidence) ? (
                                      <div className="mt-3 space-y-2">
                                        {handoffPayload.evidence.map((evidence, index) => {
                                          const item = evidence as Record<string, unknown>;
                                          return <div key={`${activeTrace.trace_id}-evidence-${index}`} className="rounded-xl border border-[#ead9c5] bg-white px-3 py-2 text-xs"><p className="font-semibold text-[#5a3b2e]">{String(item.tool_name ?? "工具来源未知")} · {String(item.title ?? item.path ?? "无标题")}</p><p className="mt-1 text-stone-600">{String(item.summary ?? item.content ?? "历史记录未保存摘要")}</p><p className="mt-1 text-stone-400">Provenance：{String(item.provenance ?? "历史记录未保存该字段")}</p></div>;
                                        })}
                                      </div>
                                    ) : null}
                                  </>
                                ) : routePayload.route_reason === "explicit_mention" ? (
                                  <><p className="mt-2">共享证据：无</p><p className="mt-1">原因：本次为直接路由，未发生 handoff，也未发生证据共享。</p></>
                                ) : <p className="mt-2">本次由默认主持 Agent 接手；历史记录未显示 handoff。</p>}
                              </div>
                            ) : null}
                            {bootstrapRecords.length > 0 ? (
                              <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4 text-sm text-emerald-950">
                                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-700">本次 Bootstrap 加载</p>
                                <p className="mt-2 text-xs text-emerald-800">仅展示访问控制清单，不展示记忆正文。Shared 与 Current Agent Private 是两个分组。</p>
                                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                  {["shared", "agent_private"].map((visibility) => <div key={visibility} className="rounded-xl border border-emerald-100 bg-white/80 p-3"><p className="text-xs font-semibold">{visibility === "shared" ? "Shared" : "Current Agent Private"}</p>{bootstrapRecords.filter((record) => record.visibility === visibility).map((record) => <p key={String(record.proposal_id)} className="mt-2 break-words text-xs text-emerald-900">{String(record.proposal_id)} · {String(record.target)} · owner: {String(record.owner_agent_id ?? "shared")} · {String(record.scope)}</p>) || null}</div>)}
                                </div>
                              </div>
                            ) : null}
                            {activeTrace.graph_retrieval ? (
                              <div className="rounded-2xl border border-sky-100 bg-sky-50 p-4 text-sm text-sky-950">
                                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-sky-500">Graph retrieval</p>
                                <p className="mt-2 font-semibold">Graph-assisted retrieval active</p>
                                <p className="mt-2">Evidence: {activeTrace.graph_retrieval.evidence_count}</p>
                                <p className="mt-1">Direct nodes: {activeTrace.graph_retrieval.direct_node_ids.length}</p>
                                <p className="mt-1">Expanded nodes shown: {displayedExpandedEvidenceCount}</p>
                                <p className="mt-1">Edges: {activeTrace.graph_retrieval.edge_types.length > 0 ? activeTrace.graph_retrieval.edge_types.join(", ") : "none"}</p>
                                <div className="mt-3 space-y-2">
                                  {activeTrace.graph_retrieval.evidence_chain?.map((item) => (
                                    <div key={item.id} className="rounded-xl border border-sky-100 bg-white/80 p-3 text-xs text-slate-700">
                                      <p className="font-semibold text-slate-900">{item.origin === "direct" ? "直接命中" : "图扩展补充"} · {item.node_type}</p>
                                      <p className="mt-1 break-words">{item.title}{item.path ? ` (${item.path})` : ""}</p>
                                      {item.summary ? <p className="mt-1 text-slate-500">{item.summary}</p> : null}
                                      {item.origin === "expanded" ? <p className="mt-1 text-sky-700">来自 {item.expanded_from_title ?? item.expanded_from ?? "历史记录未保存来源"}，经过 {item.edge_type ?? "历史记录未保存边类型"}</p> : null}
                                    </div>
                                  ))}
                                </div>
                                {displayedExpandedEvidenceCount === 0 ? <p className="mt-3 font-medium">本次没有可展示的扩展证据。</p> : null}
                                {activeTrace.graph_retrieval.comparison ? <div className="mt-3 rounded-xl border border-sky-200 bg-white/70 p-3 text-xs"><p className="font-semibold">Direct vs Graph（同一 query）</p><p className="mt-1">图扩展实际展示：{displayedExpandedEvidenceCount} 条节点证据。本案例仅展示实际补充，不声明通用 Recall 提升。</p><details className="mt-2"><summary className="cursor-pointer font-medium text-sky-800">查看两组真实工具结果</summary><p className="mt-2 whitespace-pre-wrap break-words text-slate-600"><span className="font-semibold">Direct</span>{"\n"}{activeTrace.graph_retrieval.comparison.direct_result}</p><p className="mt-2 whitespace-pre-wrap break-words text-slate-600"><span className="font-semibold">Graph</span>{"\n"}{activeTrace.graph_retrieval.comparison.graph_result}</p></details></div> : null}
                              </div>
                            ) : (
                              <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-4 text-sm text-slate-500">
                                No graph retrieval metadata for this trace. Run the Graph RAG demo from Examples to populate a fresh diagnostics trace.
                              </div>
                            )}
                            {activeTrace.events.map((event, index) => (
                              <div key={`${activeTrace.trace_id}-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">{event.kind}</p>
                                <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs leading-6 text-slate-600">{JSON.stringify(event.payload, null, 2)}</pre>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="rounded-2xl border border-dashed border-slate-200 p-6 text-sm text-slate-500">Pick a trace to inspect its events.</div>
                        )}
                      </div>
                    </div>
                  </div>
                </section>
              ) : null}

              {activeTab === "settings" ? (
                <section className="mt-5 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[18px] border border-slate-200 bg-white shadow-sm">
                  <div className="shrink-0 border-b border-slate-200 px-4 py-4">
                    <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                      <div className="max-w-[28rem]">
                        <p className="text-sm font-medium text-slate-900">Request settings</p>
                        <p className="mt-1 text-xs leading-5 text-slate-500">These fields are sent with each chat request. Leave API Key empty to use the backend default.</p>
                        <p className="mt-2 text-xs text-slate-400">{settingsSavedAt ? `Auto-saved locally at ${settingsSavedAt}.` : "Auto-saves locally in this browser."} Local demo configuration only; this is not production-grade key management.</p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                        <Button className="h-9 rounded-2xl px-3" onClick={handleSaveModelSettings} type="button">
                          <Save className="mr-2 h-4 w-4" />
                          Save settings
                        </Button>
                        <Button className="h-9 rounded-2xl px-3" onClick={handleUseBackendDefaultKey} type="button" variant="outline">
                          Use backend key
                        </Button>
                        <Button className="h-9 rounded-2xl px-3" onClick={handleResetModelSettings} type="button" variant="outline">
                          <RotateCcw className="mr-2 h-4 w-4" />
                          Reset
                        </Button>
                      </div>
                    </div>
                  </div>
                  <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
                    <div className="grid gap-4 pb-4 xl:grid-cols-2">
                      <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Base URL</label>
                        <Input
                          className="h-11 rounded-2xl border-slate-200 bg-slate-50/80"
                          onChange={(event) => handleModelSettingChange("baseUrl", event.target.value)}
                          placeholder="https://api.codexzh.com/v1"
                          value={modelSettings.baseUrl}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Model</label>
                        <Input
                          className="h-11 rounded-2xl border-slate-200 bg-slate-50/80"
                          onChange={(event) => handleModelSettingChange("model", event.target.value)}
                          placeholder="cc-gpt-5.6-terra"
                          value={modelSettings.model}
                        />
                      </div>
                      <div className="space-y-2 xl:col-span-2">
                        <label className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">API Key</label>
                        <Input
                          className="h-11 rounded-2xl border-slate-200 bg-slate-50/80"
                          onChange={(event) => handleModelSettingChange("apiKey", event.target.value)}
                          placeholder="Leave empty to use backend default"
                          type="password"
                          value={modelSettings.apiKey}
                        />
                        <p className="text-xs leading-5 text-slate-400">
                          If this local key has expired, clear it or click Use backend key so Mini-OpenClaw falls back to the backend default key.
                        </p>
                      </div>
                    </div>
                  </div>
                </section>
              ) : null}
            </section>
          </section>
        </div>
      </main>
      <MemoryApprovalCard
        isOpen={isMemoryReviewOpen}
        isSubmitting={isReviewingMemoryProposal}
        onApprove={() => void handleMemoryProposalDecision("approve")}
        onClose={() => setIsMemoryReviewOpen(false)}
        onReject={() => void handleMemoryProposalDecision("reject")}
        pendingCount={pendingMemoryProposals.length}
        proposal={pendingMemoryProposals[0] ?? null}
      />
    </>
  );
}
