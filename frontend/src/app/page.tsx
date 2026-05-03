"use client";

import { useState, useRef, useEffect } from "react";
import {
  Folder,
  FileText,
  Search,
  Play,
  FileUp,
  ChevronRight,
  ChevronDown,
  CheckCircle2,
  Link2,
  RotateCcw,
} from "lucide-react";
import mermaid from "mermaid";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type FileNode = {
  name: string;
  type: "folder" | "file";
  path: string;
  children?: FileNode[];
};

type Insight = {
  purpose: string;
  key_logic: string;
  analogy: string;
  end_to_end_diagram?: string;
  diagram_code?: string;
};

type TraceResult = {
  summary: string;
  key_points: string[];
  flow_steps: string[];
  end_to_end_diagram?: string;
  diagram_code: string;
  involved_files?: string[];
  relationships?: string[];
};

const FileTree = ({
  data,
  onSelect,
  depth = 0,
}: {
  data: FileNode[];
  onSelect: (path: string) => void;
  depth?: number;
}) => {
  return (
    <div className="text-sm font-mono space-y-1">
      {data.map((node, i) => (
        <FileTreeNode key={`${depth}-${i}`} node={node} onSelect={onSelect} depth={depth} />
      ))}
    </div>
  );
};

const FileTreeNode = ({
  node,
  onSelect,
  depth,
}: {
  node: FileNode;
  onSelect: (path: string) => void;
  depth: number;
}) => {
  const [isOpen, setIsOpen] = useState(depth < 1);

  if (node.type === "folder") {
    return (
      <div className="pl-2">
        <button
          type="button"
          className="flex w-full items-center gap-1.5 py-1 px-2 rounded hover:bg-zinc-800 cursor-pointer text-zinc-300 text-left"
          onClick={() => setIsOpen(!isOpen)}
        >
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <Folder size={14} className="text-blue-400 shrink-0" />
          <span className="truncate">{node.name}</span>
        </button>
        {isOpen && node.children && (
          <div className="pl-2 border-l border-zinc-800 ml-2 mt-1">
            <FileTree data={node.children} onSelect={onSelect} depth={depth + 1} />
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      type="button"
      className="flex w-full items-center gap-1.5 py-1 px-4 ml-2 rounded hover:bg-zinc-800 cursor-pointer text-zinc-400 hover:text-zinc-200 text-left"
      onClick={() => onSelect(node.path)}
    >
      <FileText size={14} className="shrink-0" />
      <span className="truncate">{node.name}</span>
    </button>
  );
};

const MermaidDiagram = ({ code, emphasis = false }: { code: string; emphasis?: boolean }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(`m-${Math.random().toString(36).slice(2)}`);

  useEffect(() => {
    if (!code || !containerRef.current) return;
    mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" });
    containerRef.current.innerHTML = "";
    const run = async () => {
      try {
        const { svg } = await mermaid.render(`${idRef.current}-${Date.now()}`, code);
        if (containerRef.current) containerRef.current.innerHTML = svg;
      } catch (e) {
        console.error("Mermaid error:", e);
        if (containerRef.current) {
          containerRef.current.textContent = "Diagram could not be rendered.";
        }
      }
    };
    void run();
  }, [code]);

  return (
    <div
      ref={containerRef}
      className={`w-full flex justify-center py-4 px-2 bg-zinc-900 rounded overflow-x-auto ${
        emphasis
          ? "min-h-[260px] border border-blue-900/40 ring-1 ring-blue-950/50"
          : "border border-zinc-800"
      }`}
    />
  );
};

async function readErrorDetail(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) {
      return data.detail.map((x: { msg?: string }) => x?.msg || "").filter(Boolean).join("; ");
    }
  } catch {
    /* ignore */
  }
  return `Request failed (${res.status})`;
}

export default function StructifyApp() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [fileStructure, setFileStructure] = useState<FileNode[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("// Select a file to view code");

  const [insight, setInsight] = useState<Insight | null>(null);
  const [traceResult, setTraceResult] = useState<TraceResult | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [githubUrl, setGithubUrl] = useState("");

  const [isLoading, setIsLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string>("");

  const resetWorkspace = () => {
    setSessionId(null);
    setFileStructure([]);
    setActiveFile(null);
    setFileContent("// Select a file to view code");
    setInsight(null);
    setTraceResult(null);
    setSearchQuery("");
    setUploadStatus("");
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsLoading(true);
    setUploadStatus("Indexing repository…");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/ingest`, { method: "POST", body: formData });
      if (!res.ok) {
        setUploadStatus(await readErrorDetail(res));
        return;
      }
      const data = await res.json();
      if (data.session_id) {
        setSessionId(data.session_id);
        setFileStructure(data.structure);
        setUploadStatus("Ready.");
      } else {
        setUploadStatus("Error processing repository.");
      }
    } catch {
      setUploadStatus("Connection failed. Is the API running?");
    } finally {
      setIsLoading(false);
      e.target.value = "";
    }
  };

  const handleGithubIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!githubUrl.trim()) return;
    setIsLoading(true);
    setUploadStatus("Fetching from GitHub…");
    const fd = new FormData();
    fd.append("github_url", githubUrl.trim());
    try {
      const res = await fetch(`${API_BASE}/ingest`, { method: "POST", body: fd });
      if (!res.ok) {
        setUploadStatus(await readErrorDetail(res));
        return;
      }
      const data = await res.json();
      if (data.session_id) {
        setSessionId(data.session_id);
        setFileStructure(data.structure);
        setUploadStatus("Ready.");
        setGithubUrl("");
      } else {
        setUploadStatus("Error processing repository.");
      }
    } catch {
      setUploadStatus("Connection failed. Is the API running?");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectFile = async (path: string) => {
    if (!sessionId) return;
    setActiveFile(path);
    setTraceResult(null);
    setInsight(null);
    setIsLoading(true);
    setFileContent("// Loading…");

    try {
      const fr = await fetch(
        `${API_BASE}/sessions/${sessionId}/file?path=${encodeURIComponent(path)}`,
      );
      if (!fr.ok) {
        setFileContent(`// Could not load file: ${await readErrorDetail(fr)}`);
        setIsLoading(false);
        return;
      }
      const fileData = await fr.json();
      setFileContent(fileData.content ?? "");

      const er = await fetch(`${API_BASE}/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, filepath: path }),
      });
      if (er.ok) {
        const data = await er.json();
        setInsight(data);
      }
    } catch (err) {
      console.error(err);
      setFileContent("// Failed to load file.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim() || !sessionId) return;

    setInsight(null);
    setActiveFile(`Trace: ${searchQuery.trim()}`);
    setFileContent("// Trace results are shown in the insight column.");
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery.trim(), session_id: sessionId }),
      });
      if (!res.ok) {
        setTraceResult({
          summary: await readErrorDetail(res),
          key_points: [],
          flow_steps: [],
          end_to_end_diagram: "graph TD\n  A[Error] --> B[Check API logs]",
          diagram_code: "graph TD\n  A[Error] --> B[Check API logs]",
        });
        return;
      }
      const data = await res.json();
      setTraceResult(data);
    } catch (err) {
      console.error(err);
      setTraceResult({
        summary: "Network error while running trace.",
        key_points: [],
        flow_steps: [],
        end_to_end_diagram: "graph TD\n  A[Offline] --> B[Retry]",
        diagram_code: "graph TD\n  A[Offline] --> B[Retry]",
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-[#0A0A0B] text-zinc-300 font-sans">
      <header className="h-14 border-b border-zinc-800 flex items-center justify-between px-6 bg-[#0F0F11] gap-4">
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-4 h-4 bg-blue-500 rounded-sm" />
          <span className="font-semibold text-zinc-100 tracking-tight">Structify</span>
          {isLoading && (
            <span className="text-[10px] uppercase tracking-wide text-zinc-500 ml-2">Working</span>
          )}
        </div>

        <form onSubmit={handleSearch} className="flex-1 max-w-2xl relative min-w-0">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={16} />
          <input
            type="search"
            name="trace"
            placeholder="Trace flow (e.g. authentication, login handler)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            disabled={!sessionId}
            className="w-full bg-[#18181B] border border-zinc-800 rounded-md py-1.5 pl-10 pr-4 text-sm focus:outline-none focus:border-zinc-600 focus:bg-[#1F1F22] disabled:opacity-50"
          />
        </form>

        <div className="flex items-center gap-2 text-xs shrink-0">
          {sessionId ? (
            <>
              <div className="flex items-center gap-1.5 text-emerald-400">
                <CheckCircle2 size={14} /> Indexed
              </div>
              <button
                type="button"
                onClick={resetWorkspace}
                className="flex items-center gap-1.5 cursor-pointer bg-[#18181B] hover:bg-[#27272A] border border-zinc-800 px-3 py-1.5 rounded-md text-zinc-300"
              >
                <RotateCcw size={14} /> New workspace
              </button>
            </>
          ) : (
            <div className="flex flex-col items-end gap-2 sm:flex-row sm:items-center">
              <form onSubmit={handleGithubIngest} className="flex items-center gap-2">
                <input
                  type="url"
                  value={githubUrl}
                  onChange={(e) => setGithubUrl(e.target.value)}
                  placeholder="https://github.com/owner/repo"
                  className="w-44 sm:w-56 bg-[#18181B] border border-zinc-800 rounded-md py-1.5 px-2 text-[11px] focus:outline-none focus:border-zinc-600"
                />
                <button
                  type="submit"
                  className="flex items-center gap-1.5 bg-[#18181B] hover:bg-[#27272A] border border-zinc-800 px-2 py-1.5 rounded-md"
                >
                  <Link2 size={14} /> Import
                </button>
              </form>
              <label className="flex items-center gap-2 cursor-pointer bg-[#18181B] hover:bg-[#27272A] border border-zinc-800 px-3 py-1.5 rounded-md">
                <FileUp size={14} />
                <span>ZIP</span>
                <input type="file" accept=".zip" className="hidden" onChange={handleFileUpload} />
              </label>
            </div>
          )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-64 border-r border-zinc-800 bg-[#0F0F11] flex flex-col shrink-0">
          <div className="p-3 border-b border-zinc-800 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
            Structure Map
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {fileStructure.length > 0 ? (
              <FileTree data={fileStructure} onSelect={handleSelectFile} />
            ) : (
              <div className="text-xs text-zinc-600 p-4 text-center leading-relaxed">
                {uploadStatus || "Load a ZIP archive or GitHub URL to map the tree."}
              </div>
            )}
          </div>
        </aside>

        <main className="flex-1 flex flex-col bg-[#0A0A0B] min-w-0">
          <div className="h-10 border-b border-zinc-800 flex items-center px-4 text-sm font-mono text-zinc-400 bg-[#0F0F11] truncate">
            {activeFile || "Editor"}
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <pre className="font-mono text-sm leading-relaxed text-zinc-300 whitespace-pre-wrap break-words">
              <code>{fileContent}</code>
            </pre>
          </div>
        </main>

        <aside className="w-[26rem] max-w-[40vw] border-l border-zinc-800 bg-[#0F0F11] flex flex-col shrink-0 min-w-[18rem]">
          <div className="p-3 border-b border-zinc-800 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
            System Insights
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-6">
            {insight && (
              <div className="space-y-4">
                <div className="space-y-1">
                  <div className="text-xs font-semibold text-zinc-500 uppercase">Purpose</div>
                  <div className="text-sm text-zinc-200 leading-relaxed bg-zinc-900 border border-zinc-800 p-3 rounded">
                    {insight.purpose}
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-xs font-semibold text-zinc-500 uppercase">Key Logic</div>
                  <div className="text-sm text-zinc-300 leading-relaxed bg-zinc-900 border border-zinc-800 p-3 rounded">
                    {insight.key_logic}
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-xs font-semibold text-zinc-500 uppercase">Analogy</div>
                  <div className="text-sm text-zinc-400 italic bg-zinc-900 border border-zinc-800 p-3 rounded border-l-2 border-l-blue-500">
                    {insight.analogy}
                  </div>
                </div>

                {(insight.end_to_end_diagram || insight.diagram_code) && (
                  <div className="space-y-2">
                    <div className="text-xs font-semibold text-blue-400/90 uppercase tracking-wide">
                      End-to-end flow (this file)
                    </div>
                    <p className="text-[11px] text-zinc-500 leading-snug">
                      Entry → symbols in this module → boundary (exports, IO, side effects).
                    </p>
                    <MermaidDiagram
                      code={insight.end_to_end_diagram || insight.diagram_code || ""}
                      emphasis
                    />
                  </div>
                )}

                {insight.diagram_code &&
                  insight.end_to_end_diagram &&
                  insight.diagram_code.trim() !== insight.end_to_end_diagram.trim() && (
                    <div className="space-y-1">
                      <div className="text-xs font-semibold text-zinc-500 uppercase">Compact map</div>
                      <MermaidDiagram code={insight.diagram_code} />
                    </div>
                  )}
              </div>
            )}

            {traceResult && (
              <div className="space-y-6">
                <div className="space-y-1">
                  <div className="text-xs font-semibold text-zinc-400 uppercase">Flow Summary</div>
                  <div className="text-sm text-zinc-200 leading-relaxed">{traceResult.summary}</div>
                </div>

                {(traceResult.end_to_end_diagram || traceResult.diagram_code) && (
                  <div className="space-y-2 rounded-lg bg-zinc-950/50 border border-zinc-800/80 p-3">
                    <div className="text-xs font-semibold text-blue-400/90 uppercase tracking-wide">
                      End-to-end flow chart
                    </div>
                    <p className="text-[11px] text-zinc-500 leading-snug">
                      Start → each module touched by this trace → outcome. Edge labels mirror execution
                      steps when available.
                    </p>
                    <MermaidDiagram
                      code={traceResult.end_to_end_diagram || traceResult.diagram_code}
                      emphasis
                    />
                  </div>
                )}

                {traceResult.key_points?.length ? (
                  <div className="space-y-2">
                    <div className="text-xs font-semibold text-zinc-500 uppercase">Key Points</div>
                    <ul className="list-disc pl-4 space-y-1 text-sm text-zinc-300">
                      {traceResult.key_points.map((p, i) => (
                        <li key={i}>{p}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {traceResult.diagram_code &&
                  traceResult.end_to_end_diagram &&
                  traceResult.diagram_code.trim() !== traceResult.end_to_end_diagram.trim() && (
                    <div className="space-y-1">
                      <div className="text-xs font-semibold text-zinc-500 uppercase">
                        Retrieval order map
                      </div>
                      <MermaidDiagram code={traceResult.diagram_code} />
                    </div>
                  )}

                {traceResult.involved_files?.length ? (
                  <div className="space-y-2">
                    <div className="text-xs font-semibold text-zinc-500 uppercase">Involved Files</div>
                    <ul className="space-y-1 text-xs font-mono text-zinc-400">
                      {traceResult.involved_files.map((f) => (
                        <li key={f}>
                          <button
                            type="button"
                            className="text-left hover:text-zinc-200 underline-offset-2 hover:underline"
                            onClick={() => handleSelectFile(f)}
                          >
                            {f}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {traceResult.relationships?.length ? (
                  <div className="space-y-2">
                    <div className="text-xs font-semibold text-zinc-500 uppercase">Relationships</div>
                    <ul className="space-y-1.5 text-sm text-zinc-300">
                      {traceResult.relationships.map((r, i) => (
                        <li
                          key={i}
                          className="bg-zinc-900 border border-zinc-800 p-2 rounded leading-relaxed"
                        >
                          {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div className="space-y-2">
                  <div className="text-xs font-semibold text-zinc-500 uppercase">Execution Steps</div>
                  <div className="space-y-2">
                    {traceResult.flow_steps.map((step, i) => (
                      <div
                        key={i}
                        className="flex gap-3 text-sm text-zinc-300 bg-zinc-900 border border-zinc-800 p-2.5 rounded items-start"
                      >
                        <div className="bg-zinc-800 text-zinc-400 w-5 h-5 flex items-center justify-center rounded text-xs shrink-0 mt-0.5">
                          {i + 1}
                        </div>
                        <div className="leading-relaxed">{step}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {!insight && !traceResult && !isLoading && (
              <div className="flex flex-col items-center justify-center h-40 text-center space-y-3">
                <Play className="text-zinc-700" size={24} />
                <p className="text-sm text-zinc-500 px-2">
                  Open a file or run a trace to see structured insights and diagrams.
                </p>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
