"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef } from "react";
import type { OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

type MonacoMarkdownEditorProps = {
  value: string;
  onChange: (value: string) => void;
  onSave: () => void;
  height?: string;
};

export function MonacoMarkdownEditor({
  value,
  onChange,
  onSave,
  height = "100%",
}: MonacoMarkdownEditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);

  const theme = useMemo(() => "vs", []);

  const handleMount = useCallback<OnMount>((instance) => {
    editorRef.current = instance;

    instance.addCommand((window.navigator.platform.includes("Mac") ? 2048 : 256) | 49, () => {
      onSave();
    });
  }, [onSave]);

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        onSave();
      }
    };

    window.addEventListener("keydown", listener);
    return () => {
      window.removeEventListener("keydown", listener);
    };
  }, [onSave]);

  return (
    <MonacoEditor
      height={height}
      language="markdown"
      onChange={(nextValue) => onChange(nextValue ?? "")}
      onMount={handleMount}
      options={{
        automaticLayout: true,
        fontSize: 13,
        lineNumbersMinChars: 3,
        minimap: { enabled: false },
        padding: { top: 12, bottom: 12 },
        renderLineHighlight: "gutter",
        roundedSelection: true,
        scrollBeyondLastLine: false,
        tabSize: 2,
        wordWrap: "on",
      }}
      theme={theme}
      value={value}
    />
  );
}
