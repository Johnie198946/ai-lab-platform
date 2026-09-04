import { useEffect, useLayoutEffect, useRef } from "react";
import gsap from "gsap";

export const useAmbientEffects = ({ rolesCount, selectedRoleId }) => {
  const cardsRef = useRef(null);
  const cursorCoreRef = useRef(null);
  const cursorGlowRef = useRef(null);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mediaQuery.matches) {
      return undefined;
    }

    const xToCore = gsap.quickTo(cursorCoreRef.current, "x", {
      duration: 0.22,
      ease: "power3.out",
    });
    const yToCore = gsap.quickTo(cursorCoreRef.current, "y", {
      duration: 0.22,
      ease: "power3.out",
    });
    const xToGlow = gsap.quickTo(cursorGlowRef.current, "x", {
      duration: 0.5,
      ease: "power3.out",
    });
    const yToGlow = gsap.quickTo(cursorGlowRef.current, "y", {
      duration: 0.5,
      ease: "power3.out",
    });

    const handleMove = (event) => {
      xToCore(event.clientX - 90);
      yToCore(event.clientY - 90);
      xToGlow(event.clientX - 180);
      yToGlow(event.clientY - 180);
    };

    window.addEventListener("pointermove", handleMove);
    return () => window.removeEventListener("pointermove", handleMove);
  }, []);

  useLayoutEffect(() => {
    if (!cardsRef.current || rolesCount === 0) {
      return undefined;
    }

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mediaQuery.matches) {
      return undefined;
    }

    const context = gsap.context(() => {
      gsap.fromTo(
        ".role-card",
        {
          opacity: 0,
          y: 18,
          scale: 0.96,
        },
        {
          opacity: 1,
          y: 0,
          scale: 1,
          duration: 0.45,
          stagger: 0.06,
          ease: "back.out(1.2)",
        },
      );

      gsap.fromTo(
        ".editor-panel",
        {
          opacity: 0,
          y: 14,
        },
        {
          opacity: 1,
          y: 0,
          duration: 0.35,
          ease: "power2.out",
        },
      );
    }, cardsRef);

    return () => context.revert();
  }, [rolesCount, selectedRoleId]);

  return {
    cardsRef,
    cursorCoreRef,
    cursorGlowRef,
  };
};

export const handleCardPointerMove = (event) => {
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  event.currentTarget.style.setProperty("--pointer-x", `${x}px`);
  event.currentTarget.style.setProperty("--pointer-y", `${y}px`);
};
