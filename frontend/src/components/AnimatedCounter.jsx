import { useEffect, useRef, useState } from "react";

/**
 * Animated counter that counts up from 0 to `end` when scrolled into view.
 * @param {{ end: number, duration?: number, suffix?: string, prefix?: string }} props
 */
export default function AnimatedCounter({ end, duration = 1800, suffix = "", prefix = "" }) {
  const ref = useRef(null);
  const [value, setValue] = useState(0);
  const [hasAnimated, setHasAnimated] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || hasAnimated) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasAnimated(true);
          observer.disconnect();

          const startTime = performance.now();
          const step = (now) => {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            // easeOutQuart for smooth deceleration
            const eased = 1 - Math.pow(1 - progress, 4);
            setValue(Math.round(eased * end));

            if (progress < 1) {
              requestAnimationFrame(step);
            }
          };
          requestAnimationFrame(step);
        }
      },
      { threshold: 0.3 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [end, duration, hasAnimated]);

  return (
    <span ref={ref} className="landing-counter-value">
      {prefix}{value.toLocaleString()}{suffix}
    </span>
  );
}
