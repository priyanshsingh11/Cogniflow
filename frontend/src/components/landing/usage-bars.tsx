"use client";

import type { CSSProperties } from "react";
import { useInView } from "./use-in-view";

const DAYS = [32, 41, 38, 58, 49, 72, 66, 84, 61, 77, 93, 70, 88, 100];
const FAIL = [2, 1, 3, 4, 1, 6, 2, 5, 2, 3, 7, 2, 3, 4];

export function UsageBars() {
  const [ref, seen] = useInView<HTMLDivElement>(0.3);
  return (
    <div ref={ref} className="flex h-28 items-end gap-1.5" role="img" aria-label="Sample chart of daily model attempts with failed attempts highlighted">
      {DAYS.map((h, i) => (
        <div key={i} className="relative flex-1" style={{ height: `${h}%` }}>
          <div
            className={`absolute inset-0 rounded-t-[3px] bg-ink/85 ${seen ? "bar-grow" : "scale-y-0"}`}
            style={{ "--d": `${i * 45}ms` } as CSSProperties}
          >
            <div className="absolute inset-x-0 top-0 rounded-t-[3px] bg-signal" style={{ height: `${FAIL[i] * 2.2}%`, minHeight: 3 }} />
          </div>
        </div>
      ))}
    </div>
  );
}
