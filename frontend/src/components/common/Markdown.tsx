import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { DiffView } from "./DiffView";

const components: Components = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
  pre: ({ children }) => <>{children}</>,
  code: ({ node: _node, className, children, ...props }) => {
    const lang = /language-(\w+)/.exec(className ?? "")?.[1];
    const text = String(children ?? "");
    const isBlock = Boolean(lang) || text.includes("\n");
    if (lang === "diff") return <DiffView diff={text} maxHeight="28rem" />;
    if (isBlock) {
      return (
        <pre className="overflow-x-auto rounded-md border border-line bg-sunken p-3 text-[0.8rem] leading-relaxed scroll-thin">
          <code className={className} {...props}>
            {text.replace(/\n$/, "")}
          </code>
        </pre>
      );
    }
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  },
};

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("prose-rcp text-sm", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
