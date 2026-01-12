import { useEffect, useRef, useCallback } from 'react';

interface Node {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  baseOpacity: number;
  firing: boolean;
  fireIntensity: number;
}

interface NeuralBackgroundProps {
  isAgentResponding: boolean;
}

const NODE_COUNT = 40;
const CONNECTION_DISTANCE = 150;
const NODE_SPEED = 0.3;
const FIRE_DECAY = 0.02;

export function NeuralBackground({ isAgentResponding }: NeuralBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodesRef = useRef<Node[]>([]);
  const animationRef = useRef<number | null>(null);
  const wasRespondingRef = useRef(false);

  // Initialize nodes
  const initNodes = useCallback((width: number, height: number) => {
    const nodes: Node[] = [];
    for (let i = 0; i < NODE_COUNT; i++) {
      nodes.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * NODE_SPEED,
        vy: (Math.random() - 0.5) * NODE_SPEED,
        radius: Math.random() * 1.5 + 1,
        baseOpacity: Math.random() * 0.3 + 0.1,
        firing: false,
        fireIntensity: 0,
      });
    }
    nodesRef.current = nodes;
  }, []);

  // Trigger firing effect
  const triggerFiring = useCallback(() => {
    const nodes = nodesRef.current;
    const numToFire = Math.floor(Math.random() * 4) + 2;
    const indices = new Set<number>();

    while (indices.size < numToFire) {
      indices.add(Math.floor(Math.random() * nodes.length));
    }

    let delay = 0;
    indices.forEach((index) => {
      setTimeout(() => {
        if (nodesRef.current[index]) {
          nodesRef.current[index].firing = true;
          nodesRef.current[index].fireIntensity = 1;
        }
      }, delay);
      delay += 80;
    });
  }, []);

  // Animation loop
  const animate = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height } = canvas;
    const nodes = nodesRef.current;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Update and draw nodes
    nodes.forEach((node, i) => {
      // Update position
      node.x += node.vx;
      node.y += node.vy;

      // Bounce off edges
      if (node.x < 0 || node.x > width) node.vx *= -1;
      if (node.y < 0 || node.y > height) node.vy *= -1;

      // Keep in bounds
      node.x = Math.max(0, Math.min(width, node.x));
      node.y = Math.max(0, Math.min(height, node.y));

      // Update firing intensity
      if (node.firing) {
        node.fireIntensity -= FIRE_DECAY;
        if (node.fireIntensity <= 0) {
          node.firing = false;
          node.fireIntensity = 0;
        }
      }

      // Draw connections to nearby nodes
      for (let j = i + 1; j < nodes.length; j++) {
        const other = nodes[j];
        const dx = other.x - node.x;
        const dy = other.y - node.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < CONNECTION_DISTANCE) {
          const opacity = (1 - distance / CONNECTION_DISTANCE) * 0.15;
          const firing = node.firing || other.firing;
          const fireIntensity = Math.max(node.fireIntensity, other.fireIntensity);

          if (firing) {
            // Blue glow when firing
            ctx.strokeStyle = `rgba(59, 130, 246, ${opacity + fireIntensity * 0.4})`;
            ctx.lineWidth = 1 + fireIntensity;
          } else {
            ctx.strokeStyle = `rgba(75, 85, 99, ${opacity})`;
            ctx.lineWidth = 0.5;
          }

          ctx.beginPath();
          ctx.moveTo(node.x, node.y);
          ctx.lineTo(other.x, other.y);
          ctx.stroke();
        }
      }
    });

    // Draw nodes on top
    nodes.forEach((node) => {
      const opacity = node.baseOpacity + node.fireIntensity * 0.6;

      if (node.firing) {
        // Outer glow
        const gradient = ctx.createRadialGradient(
          node.x,
          node.y,
          0,
          node.x,
          node.y,
          node.radius * 8
        );
        gradient.addColorStop(0, `rgba(59, 130, 246, ${node.fireIntensity * 0.5})`);
        gradient.addColorStop(1, 'rgba(59, 130, 246, 0)');
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius * 8, 0, Math.PI * 2);
        ctx.fill();

        // Core
        ctx.fillStyle = `rgba(59, 130, 246, ${opacity})`;
      } else {
        ctx.fillStyle = `rgba(107, 114, 128, ${opacity})`;
      }

      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fill();
    });

    animationRef.current = requestAnimationFrame(animate);
  }, []);

  // Handle resize
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handleResize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();

      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;

      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.scale(dpr, dpr);
      }

      // Reinitialize nodes for new size
      initNodes(rect.width, rect.height);
    };

    handleResize();
    window.addEventListener('resize', handleResize);

    return () => window.removeEventListener('resize', handleResize);
  }, [initNodes]);

  // Start animation
  useEffect(() => {
    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [animate]);

  // Trigger firing when agent starts responding
  useEffect(() => {
    if (isAgentResponding && !wasRespondingRef.current) {
      triggerFiring();
    }
    wasRespondingRef.current = isAgentResponding;
  }, [isAgentResponding, triggerFiring]);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 w-full h-full pointer-events-none"
      style={{ opacity: 0.6 }}
    />
  );
}
