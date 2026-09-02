import { AlertCircle, CheckCircle2, FileUp, LoaderCircle } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { extractDocument } from "../lib/api";
import type { EvidenceCategory } from "../types";


interface Props {
  category: EvidenceCategory;
  sessionId: string;
  onExtracted: (category: EvidenceCategory, fields: Record<string, string | number | null>) => boolean;
  sampleUrl?: string;
  sampleFileName?: string;
}

type UploadState = "idle" | "uploading" | "verified" | "extracted" | "review" | "error";

export default function EvidenceUpload({ category, sessionId, onExtracted, sampleUrl, sampleFileName }: Props) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<UploadState>("idle");
  const [fileName, setFileName] = useState("");

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setFileName(file.name);
    if (file.size > 10 * 1024 * 1024) {
      setState("error");
      return;
    }
    setState("uploading");
    try {
      const result = await extractDocument(sessionId, category, file);
      const applied = result.status !== "failed" && onExtracted(category, result.fields);
      setState(
        result.status === "failed"
          ? "error"
          : result.status !== "extracted" || !applied
            ? "review"
            : result.upload_id
              ? "verified"
              : "extracted",
      );
    } catch {
      setState("error");
    }
  };

  const handleSample = async () => {
    if (!sampleUrl) return;
    const name = sampleFileName || sampleUrl.split("/").pop() || "sample.pdf";
    setFileName(name);
    setState("uploading");
    try {
      const response = await fetch(sampleUrl);
      if (!response.ok) throw new Error("sample unavailable");
      const blob = await response.blob();
      await handleFile(new File([blob], name, { type: blob.type || "application/pdf" }));
    } catch {
      setState("error");
    }
  };

  const statusText = {
    idle: "",
    uploading: t("collect.uploading"),
    verified: t("collect.uploadVerified"),
    extracted: t("collect.uploadExtractedOnly"),
    review: t("collect.uploadReview"),
    error: t("collect.uploadError"),
  }[state];

  return (
    <div className={`evidence-upload ${state}`}>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,application/pdf"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          void handleFile(file);
        }}
      />
      <button className="upload-trigger" type="button" onClick={() => inputRef.current?.click()} disabled={state === "uploading"}>
        {state === "uploading" ? <LoaderCircle className="spin" size={18} /> : <FileUp size={18} />}
        <span><strong>{t("collect.upload")}</strong><small>{fileName || t("collect.uploadHint")}</small></span>
      </button>
      {sampleUrl && (
        <button className="sample-upload" type="button" onClick={() => void handleSample()} disabled={state === "uploading"}>
          {t("collect.sampleUpload")}
        </button>
      )}
      {statusText && (
        <p aria-live="polite">
          {state === "verified" ? <CheckCircle2 size={15} /> : state === "uploading" ? null : <AlertCircle size={15} />}
          {statusText}
        </p>
      )}
    </div>
  );
}
