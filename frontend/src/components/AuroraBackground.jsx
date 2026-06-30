import { useEffect, useRef } from 'react';

export default function AuroraBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let width = window.innerWidth;
    let height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;

    const orbs = [
      { x: 0.15, y: 0.3,  r: 0.45, color: [99, 102, 241],  speed: 0.00018, phase: 0 },
      { x: 0.85, y: 0.15, r: 0.35, color: [139, 92, 246],   speed: 0.00022, phase: 2.1 },
      { x: 0.5,  y: 0.85, r: 0.4,  color: [168, 85, 247],   speed: 0.00015, phase: 4.2 },
      { x: 0.75, y: 0.6,  r: 0.28, color: [79, 70, 229],    speed: 0.00025, phase: 1.0 },
      { x: 0.25, y: 0.7,  r: 0.3,  color: [109, 40, 217],   speed: 0.0002,  phase: 3.1 },
    ];

    let animId;
    let t = 0;

    function draw(ts) {
      t = ts;
      ctx.clearRect(0, 0, width, height);

      orbs.forEach(orb => {
        const drift = Math.sin(ts * orb.speed + orb.phase);
        const driftY = Math.cos(ts * orb.speed * 1.3 + orb.phase);
        const cx = (orb.x + drift * 0.08) * width;
        const cy = (orb.y + driftY * 0.06) * height;
        const radius = orb.r * Math.max(width, height);

        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
        const [r, g, b] = orb.color;
        grad.addColorStop(0, `rgba(${r},${g},${b},0.22)`);
        grad.addColorStop(0.4, `rgba(${r},${g},${b},0.1)`);
        grad.addColorStop(1, `rgba(${r},${g},${b},0)`);

        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();
      });

      animId = requestAnimationFrame(draw);
    }

    animId = requestAnimationFrame(draw);

    const onResize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width;
      canvas.height = height;
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0, left: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        pointerEvents: 'none',
      }}
    />
  );
}
