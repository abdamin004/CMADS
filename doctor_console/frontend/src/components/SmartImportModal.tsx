import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Sparkles,
  Loader2,
  FileText,
  FileUp,
  Image as ImageIcon,
} from "lucide-react";
import { extractText, extractFile } from "../api";
import type { ExtractResponse } from "../types";

interface Props {
  onClose:   () => void;
  onExtract: (r: ExtractResponse) => void; // hand off to PreviewMergeModal
}

type Tab = "text" | "file" | "image";

function FileDropZone({ accept, onFile, file }: {
  accept: string;
  onFile: (f: File | null) => void;
  file: File | null;
}) {
  const [dragOver, setDragOver] = useState(false);
  function pickFromList(files: FileList | null) {
    if (!files || files.length === 0) return;
    onFile(files[0]);
  }
  return (
    <label
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => { e.preventDefault(); setDragOver(false); pickFromList(e.dataTransfer.files); }}
      className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed px-6 py-10 text-center transition
                 ${dragOver ? "border-emerald-500 bg-emerald-600/5"
                            : "border-slate-700 hover:border-slate-600 bg-slate-950"}`}
    >
      <FileUp size={28} className="text-slate-500" />
      <div className="text-sm text-slate-200">
        {file
          ? <><span className="font-medium">{file.name}</span> <span className="text-slate-500">· {(file.size / 1024).toFixed(1)} KB</span></>
          : "Drop a file here or click to browse"}
      </div>
      <div className="text-xs text-slate-500">.pdf · .json (FHIR)</div>
      <input type="file" accept={accept} className="hidden"
             onChange={(e) => pickFromList(e.target.files)} />
    </label>
  );
}

export function SmartImportModal({ onClose, onExtract }: Props) {
  const [tab, setTab]     = useState<Tab>("text");
  const [text, setText]   = useState("");
  const [file, setFile]   = useState<File | null>(null);
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canRun =
    ((tab === "text" && text.trim().length > 0) ||
     (tab === "file" && file !== null))
    && !busy;

  async function runExtract() {
    if (!canRun) return;
    setBusy(true);
    setError(null);
    try {
      let result: ExtractResponse;
      if (tab === "text") {
        result = await extractText(text);
      } else if (tab === "file" && file) {
        result = await extractFile(file);
      } else {
        return;
      }
      onExtract(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Extraction failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <motion.div
        className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-xl border border-slate-800 bg-slate-900 shadow-2xl"
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 12, scale: 0.98 }}
        transition={{ duration: 0.18, ease: "easeOut" }}
      >
        {/* Header */}
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-emerald-400" />
            <h2 className="text-lg font-medium text-slate-100">Smart import</h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-100 transition-colors"
          >
            <X size={18} />
          </button>
        </header>

        {/* Tab strip */}
        <div className="border-b border-slate-800 px-5 pt-3 pb-0">
          <div className="segmented" role="tablist">
            <button
              role="tab"
              aria-selected={tab === "text"}
              onClick={() => setTab("text")}
              className={`segmented__btn${tab === "text" ? " segmented__btn--active" : ""}`}
            >
              <FileText size={14} />
              Paste text
            </button>
            <button
              role="tab"
              aria-selected={tab === "file"}
              onClick={() => setTab("file")}
              className={`segmented__btn${tab === "file" ? " segmented__btn--active" : ""}`}
            >
              <FileUp size={14} />
              Upload file
            </button>
            <button
              role="tab"
              aria-selected={tab === "image"}
              disabled
              className="segmented__btn opacity-40 cursor-not-allowed"
              title="Coming in Phase 3"
            >
              <ImageIcon size={14} />
              Image
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {tab === "text" && (
            <div className="space-y-2">
              <label
                htmlFor="smart-paste"
                className="block text-xs uppercase tracking-wide text-slate-400"
              >
                Paste a chart note, lab report, or any clinical text
              </label>
              <textarea
                id="smart-paste"
                rows={14}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={`e.g. 70 y/o F with T2DM on metformin 500 mg BID.\nHbA1c 8.2%, eGFR 42, BMI 32.\nActive: hypertension, hyperlipidemia.`}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 font-mono resize-y"
              />
              <div className="flex justify-between text-xs text-slate-500">
                <span>{text.length.toLocaleString()} chars</span>
                <span>Cap: 32 kB</span>
              </div>
            </div>
          )}

          {tab === "file" && (
            <div className="space-y-3">
              <label className="block text-xs uppercase tracking-wide text-slate-400">
                Drop a PDF or FHIR JSON file
              </label>
              <FileDropZone
                accept=".pdf,.json,application/pdf,application/json,application/fhir+json"
                onFile={(f) => setFile(f)}
                file={file}
              />
              <p className="text-xs text-slate-500">
                PDFs are parsed with pdfplumber; FHIR JSON is parsed structurally without an LLM call.
                5 MB cap.
              </p>
            </div>
          )}
        </div>

        {/* Error */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="border-t border-rose-700/40 bg-rose-900/20 px-5 py-2 text-sm text-rose-300"
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Footer */}
        <footer className="flex items-center justify-end gap-3 border-t border-slate-800 px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={runExtract}
            disabled={!canRun}
            className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40 transition-colors"
          >
            {busy ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Extracting…
              </>
            ) : (
              <>Extract →</>
            )}
          </button>
        </footer>
      </motion.div>
    </motion.div>
  );
}
