import { useEffect, useRef } from "react";

/**
 * Animated particle canvas background.
 * Renders floating, gently connected dots in peach/amber tones.
 * Designed for dark hero sections.
 */
export default function ParticleBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    let animationId;
    let particles = [];

    const PARTICLE_COUNT = 60;
    const CONNECTION_DISTANCE = 140;
    const COLORS = [
      "rgba(255,148,102,",  // peach
      "rgba(255,185,152,",  // peach-light
      "rgba(255,127,83,",   // peach-strong
      "rgba(255,210,180,",  // warm cream
    ];

    function resize() {
      const rect = canvas.parentElement.getBoundingClientRect();
      canvas.width = rect.width;
      canvas.height = rect.height;
    }

    function createParticle() {
      const colorBase = COLORS[Math.floor(Math.random() * COLORS.length)];
      const alpha = 0.15 + Math.random() * 0.35;
      return {
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        radius: 1.2 + Math.random() * 2.2,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        color: colorBase,
        alpha,
      };
    }

    function init() {
      resize();
      particles = Array.from({ length: PARTICLE_COUNT }, createParticle);
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Connections
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < CONNECTION_DISTANCE) {
            const opacity = (1 - dist / CONNECTION_DISTANCE) * 0.12;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(255,148,102,${opacity})`;
            ctx.lineWidth = 0.6;
            ctx.stroke();
          }
        }
      }

      // Particles
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;

        // Wrap around edges
        if (p.x < -10) p.x = canvas.width + 10;
        if (p.x > canvas.width + 10) p.x = -10;
        if (p.y < -10) p.y = canvas.height + 10;
        if (p.y > canvas.height + 10) p.y = -10;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `${p.color}${p.alpha})`;
        ctx.fill();
      }

      animationId = requestAnimationFrame(draw);
    }

    init();
    draw();

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas.parentElement);

    return () => {
      cancelAnimationFrame(animationId);
      resizeObserver.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="particle-canvas"
      aria-hidden="true"
    />
  );
}
