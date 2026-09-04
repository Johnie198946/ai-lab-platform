import React from 'react';
import { motion } from 'framer-motion';

const Orb = ({ 
  color = "rgba(100, 150, 255, 0.4)", 
  size = 300, 
  blur = 60,
  speed = 10 
}) => {
  return (
    <motion.div
      animate={{
        y: [0, -30, 0, 30, 0],
        x: [0, 20, 0, -20, 0],
        scale: [1, 1.05, 1, 0.95, 1],
      }}
      transition={{
        duration: speed,
        repeat: Infinity,
        ease: "easeInOut",
      }}
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: `radial-gradient(circle at 30% 30%, ${color}, transparent)`,
        filter: `blur(${blur}px)`,
        position: "absolute",
        zIndex: 0,
        pointerEvents: "none"
      }}
    />
  );
};

export default Orb;
