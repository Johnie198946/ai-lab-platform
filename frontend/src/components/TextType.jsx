import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';

const TextType = ({ text = "", speed = 50, className = "", delay = 0 }) => {
  const [displayedText, setDisplayedText] = useState("");

  useEffect(() => {
    setDisplayedText("");
    
    let currentIndex = 0;
    let timeoutId;
    
    const typeNextChar = () => {
      if (currentIndex < text.length) {
        setDisplayedText(text.substring(0, currentIndex + 1));
        currentIndex++;
        timeoutId = setTimeout(typeNextChar, speed);
      }
    };

    if (delay > 0) {
      timeoutId = setTimeout(typeNextChar, delay);
    } else {
      typeNextChar();
    }

    return () => clearTimeout(timeoutId);
  }, [text, speed, delay]);

  return (
    <motion.span 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className={className}
    >
      {displayedText}
      <motion.span
        animate={{ opacity: [0, 1, 0] }}
        transition={{ repeat: Infinity, duration: 0.8 }}
        className="inline-block w-[2px] h-[1em] bg-current align-middle ml-[2px]"
      />
    </motion.span>
  );
};

export default TextType;
