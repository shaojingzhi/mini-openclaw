import { Bot, FolderCode, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const features = [
  {
    title: "Transparent memory",
    description: "Markdown and JSON files stay editable and visible to the operator.",
    icon: FolderCode,
  },
  {
    title: "Skill-first agenting",
    description: "Core tools stay small while capabilities expand through readable SKILL.md files.",
    icon: Sparkles,
  },
  {
    title: "Local operator loop",
    description: "FastAPI and Next.js run as separate local processes for direct inspection.",
    icon: Bot,
  },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(58,89,255,0.14),_transparent_40%),linear-gradient(180deg,#fdfdfd_0%,#f5f7fb_100%)] px-6 py-10 text-foreground">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl flex-col justify-between rounded-[32px] border border-white/70 bg-white/70 p-8 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur-xl">
        <section className="grid gap-10 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <div className="space-y-6">
            <p className="text-sm font-medium uppercase tracking-[0.35em] text-primary/70">Next.js 14 Frontend</p>
            <div className="space-y-4">
              <h1 className="max-w-3xl text-5xl font-semibold tracking-tight text-slate-950 sm:text-6xl">
                mini OpenClaw is ready for the UI stories.
              </h1>
              <p className="max-w-2xl text-lg leading-8 text-slate-600">
                This scaffold provides the App Router, Tailwind theme tokens, shadcn baseline components, and Lucide icons needed for the IDE-style interface.
              </p>
            </div>
            <div className="flex max-w-xl flex-col gap-3 rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm sm:flex-row">
              <Input defaultValue="http://localhost:8002" readOnly aria-label="Backend API URL" />
              <Button className="sm:min-w-36">Backend Ready</Button>
            </div>
          </div>

          <div className="grid gap-4">
            {features.map(({ title, description, icon: Icon }) => (
              <article key={title} className="rounded-3xl border border-slate-200/80 bg-white/80 p-6 shadow-sm">
                <div className="mb-4 inline-flex rounded-2xl bg-primary/10 p-3 text-primary">
                  <Icon className="h-5 w-5" />
                </div>
                <h2 className="text-xl font-semibold text-slate-950">{title}</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
