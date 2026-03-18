"use client";

import { useMemo, useState } from "react";

type CsvUploadPayload = {
  file_name: string;
  row_count: number;
  column_count: number;
  columns: string[];
  preview_rows: Array<Record<string, string>>;
};

type CsvUploadProps = {
  apiBaseUrl: string;
};

export default function CsvUpload({ apiBaseUrl }: CsvUploadProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [payload, setPayload] = useState<CsvUploadPayload | null>(null);

  const previewColumns = useMemo<string[]>(() => {
    if (!payload) return [];
    if (payload.columns.length) return payload.columns;
    const first = payload.preview_rows[0];
    return first ? Object.keys(first) : [];
  }, [payload]);

  const handleUpload = async () => {
    if (!selectedFile || uploading) {
      return;
    }

    setUploading(true);
    setErrorMessage("");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch(`${apiBaseUrl}/api/v1/upload-csv`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const err = (await response.json()) as { detail?: string };
        throw new Error(err.detail || "CSV upload failed.");
      }

      const data = (await response.json()) as CsvUploadPayload;
      setPayload(data);
    } catch (error) {
      setPayload(null);
      setErrorMessage(error instanceof Error ? error.message : "CSV upload failed.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <section className="mb-6 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
      <h3 className="mb-2 text-xs uppercase tracking-wide text-slate-400">Upload CSV</h3>

      <input
        type="file"
        accept=".csv,text/csv"
        onChange={(e) => {
          const next = e.target.files?.[0] ?? null;
          setSelectedFile(next);
          setErrorMessage("");
        }}
        className="block w-full text-xs text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-slate-800 file:px-3 file:py-1 file:text-xs file:text-slate-200 hover:file:bg-slate-700"
      />

      <button
        type="button"
        onClick={() => void handleUpload()}
        disabled={!selectedFile || uploading}
        className="mt-3 w-full rounded border border-slate-700 px-3 py-2 text-xs font-medium text-slate-200 hover:border-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {uploading ? "Uploading..." : "Upload CSV"}
      </button>

      {errorMessage ? <p className="mt-2 text-xs text-red-300">{errorMessage}</p> : null}

      {payload ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-emerald-300">
            Uploaded {payload.file_name} ({payload.row_count.toLocaleString()} rows, {payload.column_count} columns)
          </p>

          <div className="max-h-44 overflow-auto rounded border border-slate-800">
            <table className="min-w-full text-xs">
              <thead className="sticky top-0 bg-slate-900">
                <tr>
                  {previewColumns.map((col) => (
                    <th key={col} className="px-2 py-1 text-left text-slate-300">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {payload.preview_rows.map((row, idx) => (
                  <tr key={`preview-${idx}`} className="border-t border-slate-800">
                    {previewColumns.map((col) => (
                      <td key={`${idx}-${col}`} className="px-2 py-1 text-slate-200">
                        {row[col] ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-slate-500">Preview shows first 8 rows.</p>
        </div>
      ) : null}
    </section>
  );
}
