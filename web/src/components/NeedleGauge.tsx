import React from "react";
import {
  angleToPoint,
  describeGaugeArc,
  marginToAngle,
} from "../lib/gauge";
import { marginLabel } from "../lib/format";
import { PARTY_COLORS } from "../lib/scales";

export interface NeedleGaugeProps {
  median: number;
  p10: number;
  p90: number;
}

export const NeedleGauge: React.FC<NeedleGaugeProps> = ({
  median,
  p10,
  p90,
}) => {
  const cx = 50;
  const cy = 44;
  const radius = 34;

  const needleAngle = marginToAngle(median);
  const needleTip = angleToPoint(cx, cy, radius - 4, needleAngle);

  const backgroundArc = describeGaugeArc(cx, cy, radius, -20, 20);
  const bandArc = describeGaugeArc(cx, cy, radius, p10, p90);

  const bandColor =
    median > 0
      ? PARTY_COLORS.D
      : median < 0
      ? PARTY_COLORS.R
      : PARTY_COLORS.I;

  return (
    <div
      className="flex flex-col items-center"
      aria-label={`Projected margin ${marginLabel(median)} (p10 ${marginLabel(
        p10
      )}, p90 ${marginLabel(p90)})`}
    >
      <svg
        viewBox="0 0 100 54"
        className="h-12 w-24 overflow-visible"
        role="img"
      >
        {/* Background semicircle track */}
        <path
          d={backgroundArc}
          fill="none"
          stroke={PARTY_COLORS.NO_DATA}
          strokeWidth={7}
          strokeLinecap="round"
        />

        {/* Center 0° tick mark */}
        <line
          x1={cx}
          y1={cy - radius - 4}
          x2={cx}
          y2={cy - radius + 4}
          stroke={PARTY_COLORS.UNCALLED}
          strokeWidth={1.2}
        />

        {/* Uncertainty arc band (p10 to p90) */}
        <path
          d={bandArc}
          fill="none"
          stroke={bandColor}
          strokeOpacity={0.45}
          strokeWidth={7}
        />

        {/* Needle at median */}
        <line
          x1={cx}
          y1={cy}
          x2={needleTip.x}
          y2={needleTip.y}
          stroke="#f8fafc"
          strokeWidth={2}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={3} fill="#f8fafc" />

        {/* Left = R, Right = D labels */}
        <text
          x={8}
          y={51}
          fontSize="8"
          fontWeight="700"
          fill={PARTY_COLORS.R}
          textAnchor="start"
        >
          R
        </text>
        <text
          x={92}
          y={51}
          fontSize="8"
          fontWeight="700"
          fill={PARTY_COLORS.D}
          textAnchor="end"
        >
          D
        </text>
      </svg>
      <span className="font-mono text-[11px] font-semibold text-slate-200">
        {marginLabel(median)}
      </span>
    </div>
  );
};
