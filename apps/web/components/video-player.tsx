"use client";

import { useRef, useState } from "react";
import { Play } from "lucide-react";

export function VideoPlayer({ src, webm, poster, title }: { src: string; webm?: string; poster?: string; title: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  return (
    <div id="demo" className="relative overflow-hidden rounded-3xl border border-line bg-black shadow-2xl shadow-brand/20">
      <video
        ref={ref} poster={poster} controls={playing} playsInline preload="metadata"
        className="aspect-video w-full" aria-label={title}
        onPlay={() => setPlaying(true)}
      >
        {webm ? <source src={webm} type="video/webm" /> : null}
        <source src={src} type="video/mp4" />
      </video>
      {!playing ? (
        <button
          type="button" aria-label={`Play ${title}`}
          onClick={() => ref.current?.play()}
          className="absolute inset-0 grid place-items-center bg-black/10 transition hover:bg-black/20"
        >
          <span className="grid size-20 place-items-center rounded-full bg-accent text-white shadow-xl">
            <Play className="ml-1 size-8" fill="currentColor" />
          </span>
        </button>
      ) : null}
    </div>
  );
}
