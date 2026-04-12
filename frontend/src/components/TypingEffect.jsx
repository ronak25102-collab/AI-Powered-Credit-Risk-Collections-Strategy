import { useEffect, useState } from "react";

/**
 * Typing animation component.
 * Types out text character-by-character with a blinking cursor.
 * @param {{ text: string, speed?: number, className?: string }} props
 */
export default function TypingEffect({ text, speed = 30, className = "" }) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    setDisplayed("");
    setDone(false);
    let i = 0;

    const interval = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(interval);
        setDone(true);
      }
    }, speed);

    return () => clearInterval(interval);
  }, [text, speed]);

  return (
    <span className={`typing-effect ${className}`}>
      {displayed}
      <span className={`typing-cursor ${done ? "typing-cursor-blink" : ""}`}>|</span>
    </span>
  );
}
