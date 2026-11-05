import React, { useState } from "react";
import { getPartyColor } from "../lib/scales";
import { initials, usePhoto } from "../lib/photos";

export interface CandidateAvatarProps {
  name: string;
  partyCode: string;
  state?: string | null;
  size?: number;
}

/** Wikipedia photo with a party-colored ring; party-colored initials when there is none. */
export const CandidateAvatar: React.FC<CandidateAvatarProps> = ({ name, partyCode, state, size = 28 }) => {
  const color = getPartyColor(partyCode);
  const { data: photo } = usePhoto(name, state);
  const [broken, setBroken] = useState(false);
  const style = { width: size, height: size, boxShadow: `0 0 0 2px ${color}` };
  if (photo && !broken) {
    return (
      <img
        src={photo}
        alt={name}
        loading="lazy"
        onError={() => setBroken(true)}
        className="shrink-0 rounded-full bg-slate-800 object-cover object-top"
        style={style}
      />
    );
  }
  return (
    <span
      role="img"
      aria-label={name}
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{ ...style, backgroundColor: color, fontSize: Math.max(10, size * 0.38) }}
    >
      {initials(name)}
    </span>
  );
};
