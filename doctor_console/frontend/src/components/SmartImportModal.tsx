import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Sparkles,
  Loader2,
  FileText,
  UploadCloud,
  FileType,
  Image as ImageIcon,
  Braces,
} from "lucide-react";
import { extractText, extractFile, extractImage } from "../api";
import type { ExtractResponse } from "../types";

interface Props {
  onClose:   () => void;
  onExtract: (r: ExtractResponse) => void; // hand off to PreviewMergeModal
}

type Tab = "text" | "upload";
type UploadKind = "pdf" | "fhir" | "image";

const ACCEPT_ALL =
  ".pdf,.json,.png,.jpg,.jpeg,.webp," +
  "application/pdf,application/json,application/fhir+json," +
  "image/png,image/jpeg,image/jpg,image/webp";

/**
 * Classify an uploaded file so we route it to the right extractor.
 * Image types → /extract kind=image (Gemini Vision).
 * PDF / JSON  → /extract kind=file (pdfplumber or structural FHIR parse).
 * The MIME may be empty for files dragged from some sources, so we fall
 * back to extension matching.
 */
function classify(file: File): UploadKind | null {
  const mime = (file.type || "").toLowerCase();
  const name = file.name.toLowerCase();
  if (mime.startsWith("image/") || /\.(png|jpe?g|webp)$/.test(name)) return "image";
  if (mime === "application/pdf" || name.endsWith(".pdf"))           return "pdf";
  if (mime.includes("json") || name.endsWith(".json"))               return "fhir";
  return null;
}

const KIND_META: Record<UploadKind, { label: string; tone: string; Icon: typeof FileType }> = {
  image: { label: "Image · lab slip",  tone: "spark",   Icon: ImageIcon },
  pdf:   { label: "PDF · pdfplumber",  tone: "accent",  Icon: FileType  },
  fhir:  { label: "FHIR JSON",         tone: "success", Icon: Braces    },
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function UnifiedDropZone({ onFile, file, kind, dragOver, setDragOver }: {
  onFile:      (f: File | null) => void;
  file:        File | null;
  kind:        UploadKind | null;
  dragOver:    boolean;
  setDragOver: (v: boolean) => void;
}) {
  function pick(files: FileList | null) {
    if (!files || files.length === 0) return;
    onFile(files[0]);
  }
  return (
    <label
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => { e.preventDefault(); setDragOver(false); pick(e.dataTransfer.files); }}
      className={`smart-drop${dragOver ? " smart-drop--over" : ""}${file ? " smart-drop--has-file" : ""}`}
    >
      <UploadCloud size={28} strokeWidth={1.4} className="smart-drop__icon" />
      <div className="smart-drop__line">
        {file
          ? <>
              <span className="smart-drop__filename">{file.name}</span>
              <span className="smart-drop__filesize">· {formatSize(file.size)}</span>
            </>
          : <>Drop a file here, or <span className="smart-drop__browse">browse</span></>
        }
      </div>
      <div className="smart-drop__formats">
        <span className="smart-drop__format-chip"><FileType  size={11} strokeWidth={1.8} /> PDF</span>
        <span className="smart-drop__format-chip"><Braces    size={11} strokeWidth={1.8} /> FHIR JSON</span>
        <span className="smart-drop__format-chip"><ImageIcon size={11} strokeWidth={1.8} /> Image</span>
      </div>
      {file && kind && (
        <span className={`demo-pill demo-pill--${KIND_META[kind].tone} smart-drop__kind`}>
          {KIND_META[kind].label}
        </span>
      )}
      <input
        type="file"
        accept={ACCEPT_ALL}
        className="hidden"
        onChange={(e) => pick(e.target.files)}
      />
    </label>
  );
}

export function SmartImportModal({ onClose, onExtract }: Props) {
  const [tab, setTab]                   = useState<Tab>("text");
  const [text, setText]                 = useState("");
  const [file, setFile]                 = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [dragOver, setDragOver]         = useState(false);
  const [busy, setBusy]                 = useState(false);
  const [error, setError]               = useState<string | null>(null);

  const kind = file ? classify(file) : null;
  // Preview only for image kinds. PDFs/JSON get a typed chip instead of a thumb.
  useEffect(() => {
    if (file && kind === "image") {
      const url = URL.createObjectURL(file);
      setImagePreview(url);
      return () => URL.revokeObjectURL(url);
    }
    setImagePreview(null);
  }, [file, kind]);

  // Reject unrecognised types up front instead of letting the upload fail
  // server-side — the inline error makes the constraint visible.
  useEffect(() => {
    if (file && kind === null) {
      setError(`"${file.name}" is not a supported file type. Use PDF, FHIR JSON, or an image.`);
    } else if (error && file && kind !== null) {
      setError(null);
    }
  }, [file, kind]); // eslint-disable-line react-hooks/exhaustive-deps

  const canRun =
    ((tab === "text"   && text.trim().length > 0) ||
     (tab === "upload" && file !== null && kind !== null))
    && !busy;

  async function runExtract() {
    if (!canRun) return;
    setBusy(true);
    setError(null);
    try {
      let result: ExtractResponse;
      if (tab === "text") {
        result = await extractText(text);
      } else if (tab === "upload" && file && kind) {
        // Single upload surface; route to the correct extractor by file kind.
        result = kind === "image" ? await extractImage(file) : await extractFile(file);
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

        {/* Tab strip — two surfaces only: paste vs. upload (file + image
            are one tab; the modal classifies the dropped file and routes
            to /extract with kind=file or kind=image automatically). */}
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
              aria-selected={tab === "upload"}
              onClick={() => setTab("upload")}
              className={`segmented__btn${tab === "upload" ? " segmented__btn--active" : ""}`}
            >
              <UploadCloud size={14} />
              Upload
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

          {tab === "upload" && (
            <div className="space-y-3">
              <label className="block text-xs uppercase tracking-wide text-slate-400">
                Drop a PDF, FHIR JSON, or photo of a lab slip
              </label>
              <UnifiedDropZone
                onFile={(f) => setFile(f)}
                file={file}
                kind={kind}
                dragOver={dragOver}
                setDragOver={setDragOver}
              />
              {file && (
                <div className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2">
                  <span className="text-xs text-slate-500">
                    {kind === "image"
                      ? "Lab rows extracted via Gemini 2.5 Flash · 10 MB cap"
                      : kind === "pdf"
                      ? "Parsed with pdfplumber · 5 MB cap"
                      : kind === "fhir"
                      ? "Parsed structurally without an LLM call · 5 MB cap"
                      : "Unsupported file type"}
                  </span>
                  <button
                    onClick={() => setFile(null)}
                    className="text-xs text-slate-500 underline hover:text-rose-400 transition-colors"
                  >
                    Choose a different file
                  </button>
                </div>
              )}
              {imagePreview && (
                <div className="overflow-hidden rounded-md border border-slate-800 bg-slate-950 p-3">
                  <img
                    src={imagePreview}
                    alt="Lab slip preview"
                    className="max-h-72 w-full rounded object-contain"
                  />
                </div>
              )}
              {!file && (
                <p className="text-xs text-slate-500">
                  PDFs use pdfplumber, FHIR JSON parses structurally without an LLM,
                  and images route to Gemini 2.5 Flash. Only labs are pulled from
                  images — demographics and conditions stay in the editor.
                </p>
              )}
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
