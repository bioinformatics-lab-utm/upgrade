import React from 'react';
import { cn } from '../../lib/utils';

export function Progress({ value, max = 100, className, indicatorClassName }) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));

  return (
    <div className={cn("relative h-4 w-full overflow-hidden rounded-full bg-secondary", className)}>
      <div
        className={cn(
          "h-full transition-all duration-300 ease-in-out",
          indicatorClassName || "bg-primary"
        )}
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}

export function QualityScore({ score, label }) {
  const getColor = (score) => {
    if (score >= 80) return 'bg-green-500';
    if (score >= 60) return 'bg-blue-500';
    if (score >= 40) return 'bg-yellow-500';
    if (score >= 20) return 'bg-orange-500';
    return 'bg-red-500';
  };

  const getTextColor = (score) => {
    if (score >= 80) return 'text-green-700';
    if (score >= 60) return 'text-blue-700';
    if (score >= 40) return 'text-yellow-700';
    if (score >= 20) return 'text-orange-700';
    return 'text-red-700';
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        <span className={cn("text-2xl font-bold", getTextColor(score))}>
          {score}
        </span>
      </div>
      <Progress
        value={score}
        max={100}
        indicatorClassName={getColor(score)}
      />
    </div>
  );
}
