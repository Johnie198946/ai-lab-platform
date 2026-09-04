import React from 'react';
import './BorderGlow.css';

export default function BorderGlow({ children, onClick }) {
  return (
    <div className="border-glow-card" onClick={onClick}>
      <div className="border-glow-content">
        {children}
      </div>
    </div>
  );
}