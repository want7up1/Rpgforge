type JsonBlockProps = {
  data: unknown;
};

export function JsonBlock({ data }: JsonBlockProps) {
  return (
    <pre className="app-wrap-text max-h-72 overflow-auto whitespace-pre-wrap rounded border border-[color:var(--border)] bg-[#f2f5ef] p-3 font-mono text-[11px] leading-5 text-[color:var(--foreground)] sm:max-h-96 sm:p-4 sm:text-xs">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
