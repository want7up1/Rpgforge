type JsonBlockProps = {
  data: unknown;
};

export function JsonBlock({ data }: JsonBlockProps) {
  return (
    <pre className="px-wrap max-h-72 overflow-auto whitespace-pre-wrap border-2 border-[color:var(--border)] bg-[#04100a] p-3 font-mono text-[11px] leading-5 text-[color:var(--phosphor-dim)] sm:max-h-96 sm:p-4 sm:text-xs">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
