import { useEffect, useState } from "react";

/**
 * Thin animated progress bar at the top of the viewport.
 * Shows during API loading. Pass `loading={true}` to activate.
 */
export default function TopProgressBar({ loading }) {
  const [visible, setVisible] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (loading) {
      setVisible(true);
      setProgress(15);

      const t1 = setTimeout(() => setProgress(45), 300);
      const t2 = setTimeout(() => setProgress(70), 800);
      const t3 = setTimeout(() => setProgress(85), 1500);

      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
        clearTimeout(t3);
      };
    }

    // Finish animation
    setProgress(100);
    const hide = setTimeout(() => {
      setVisible(false);
      setProgress(0);
    }, 350);

    return () => clearTimeout(hide);
  }, [loading]);

  if (!visible) return null;

  return (
    <div className="top-progress-bar" aria-hidden="true">
      <div
        className="top-progress-fill"
        style={{ width: `${progress}%` }}
      />
    </div>
  );
}
