import { createContext, useCallback, useContext, useState } from "react";

const ToastContext = createContext(null);

let toastIdCounter = 0;

/**
 * Global toast notification provider.
 * Wrap the app with <ToastProvider> and call useToast() in any child.
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = "info", duration = 4000) => {
    const id = ++toastIdCounter;
    setToasts((prev) => [...prev, { id, message, type }]);

    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, duration);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}

      {/* Toast stack — fixed bottom-right */}
      <div className="toast-container" aria-live="polite">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast toast-${toast.type}`}
            role="alert"
          >
            <span className="toast-icon">
              {toast.type === "success" ? "✓" : toast.type === "error" ? "✕" : "ℹ"}
            </span>
            <span className="toast-message">{toast.message}</span>
            <button
              className="toast-close"
              onClick={() => removeToast(toast.id)}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/**
 * Hook to trigger toast notifications from any component.
 * @returns {{ addToast: (message: string, type?: 'success'|'error'|'info', duration?: number) => void }}
 */
export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
