"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode
} from "react";

type ConfirmRequest = {
  kind: "confirm";
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  resolve: (value: boolean) => void;
};

type PromptRequest = {
  kind: "prompt";
  message: string;
  defaultValue?: string;
  confirmLabel?: string;
  danger?: boolean;
  resolve: (value: string | null) => void;
};

type DialogRequest = ConfirmRequest | PromptRequest;

type PixelDialogApi = {
  confirm: (message: string, options?: { confirmLabel?: string; danger?: boolean }) => Promise<boolean>;
  prompt: (
    message: string,
    options?: { defaultValue?: string; confirmLabel?: string; danger?: boolean }
  ) => Promise<string | null>;
};

const PixelDialogContext = createContext<PixelDialogApi | null>(null);

export function usePixelDialog(): PixelDialogApi {
  const api = useContext(PixelDialogContext);
  if (!api) {
    throw new Error("usePixelDialog 必须在 <PixelDialogProvider> 内使用");
  }
  return api;
}

export function PixelDialogProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<DialogRequest | null>(null);

  const confirm = useCallback<PixelDialogApi["confirm"]>(
    (message, options) =>
      new Promise<boolean>((resolve) => {
        setRequest({
          kind: "confirm",
          message,
          confirmLabel: options?.confirmLabel,
          danger: options?.danger,
          resolve
        });
      }),
    []
  );

  const prompt = useCallback<PixelDialogApi["prompt"]>(
    (message, options) =>
      new Promise<string | null>((resolve) => {
        setRequest({
          kind: "prompt",
          message,
          defaultValue: options?.defaultValue,
          confirmLabel: options?.confirmLabel,
          danger: options?.danger,
          resolve
        });
      }),
    []
  );

  function close(value: boolean | string | null) {
    if (!request) return;
    if (request.kind === "confirm") {
      request.resolve(value === true);
    } else {
      request.resolve(typeof value === "string" ? value : null);
    }
    setRequest(null);
  }

  return (
    <PixelDialogContext.Provider value={{ confirm, prompt }}>
      {children}
      {request ? <PixelDialog request={request} onClose={close} /> : null}
    </PixelDialogContext.Provider>
  );
}

function PixelDialog({
  request,
  onClose
}: {
  request: DialogRequest;
  onClose: (value: boolean | string | null) => void;
}) {
  const [text, setText] = useState(request.kind === "prompt" ? (request.defaultValue ?? "") : "");
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const previousFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (request.kind === "prompt") {
      inputRef.current?.focus();
      inputRef.current?.select();
    } else {
      confirmButtonRef.current?.focus();
    }
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose(null);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();
    };
  }, [onClose, request.kind]);

  function handleDialogKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  const confirmLabel = request.confirmLabel ?? "确认";
  const confirmClass = request.danger ? "px-btn px-btn-danger" : "px-btn px-btn-primary";

  return (
    <div aria-modal="true" className="px-modal-overlay" role="dialog" aria-label={request.message}>
      <button
        aria-label="取消"
        className="absolute inset-0 cursor-default"
        onClick={() => onClose(null)}
        type="button"
      />
      <div
        className="px-modal max-w-md"
        onKeyDown={handleDialogKeyDown}
        ref={dialogRef}
      >
        <p className="px-heading text-sm">系统询问</p>
        <p className="px-wrap mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--muted)]">
          {request.message}
        </p>
        {request.kind === "prompt" ? (
          <input
            className="px-input mt-3"
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onClose(text);
              }
            }}
            ref={inputRef}
            value={text}
          />
        ) : null}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button className="px-btn" onClick={() => onClose(null)} type="button">
            取消
          </button>
          <button
            className={confirmClass}
            onClick={() => onClose(request.kind === "prompt" ? text : true)}
            ref={confirmButtonRef}
            type="button"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
