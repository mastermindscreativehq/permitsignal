import type { ReactNode } from "react";

export function GlassCard({
  children,
  className = "",
  hover = false,
  as: Component = "div",
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  as?: "div" | "section" | "article";
}) {
  return (
    <Component className={`panel ${hover ? "panel-hover" : ""} ${className}`}>
      {children}
    </Component>
  );
}
