import React from "react";
import { useCountUp } from "../lib/useCountUp";

/** A number that counts up to its new value when it changes (respects reduced motion). */
export const Num: React.FC<{
  value: number;
  decimals?: number;
  suffix?: string;
  format?: boolean;
  className?: string;
}> = ({ value, decimals = 0, suffix = "", format = false, className }) => {
  const v = useCountUp(value);
  const text = format
    ? Math.round(v).toLocaleString("en-US")
    : v.toFixed(decimals);
  return (
    <span className={`tabular-nums ${className ?? ""}`}>
      {text}
      {suffix}
    </span>
  );
};
