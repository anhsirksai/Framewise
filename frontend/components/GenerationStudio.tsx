"use client";

import { useEffect, useState } from "react";
import {
  Badge,
  Box,
  Button,
  Flex,
  HStack,
  Input,
  Spinner,
  Text,
  Textarea,
  VStack,
} from "@chakra-ui/react";
import { Clapperboard, Sparkles } from "lucide-react";
import { API_BASE } from "@/lib/config";
import { friendlyError } from "@/lib/errors";

interface ThemeSummary {
  id: string;
  name: string;
  prompt: string;
  source_videos: string[];
  rough_cut_count: number;
}

interface RoughCutScene {
  order: number;
  title: string;
  purpose: string;
  source_video?: string;
  video_id?: string;
  start_sec?: number | null;
  end_sec?: number | null;
  voiceover?: string;
  on_screen_text?: string;
}

interface RoughCut {
  id: string;
  title: string;
  prompt: string;
  storyline: string;
  theme_dna?: string[];
  scenes?: RoughCutScene[];
  do_rules?: string[];
  dont_rules?: string[];
  rendered_video?: {
    url: string;
    path: string;
  } | null;
  render_error?: string | null;
}

function fmt(sec?: number | null): string {
  if (sec == null) return "--:--";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function artifactUrl(path: string): string {
  if (path.startsWith("http")) return path;
  return `${API_BASE.replace("/api", "")}${path}`;
}

export function GenerationStudio() {
  const [prompt, setPrompt] = useState("Create a 30-second marketing reel from the strongest product moments.");
  const [theme, setTheme] = useState("Marketing reel");
  const [duration, setDuration] = useState("45");
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [roughCut, setRoughCut] = useState<RoughCut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/generation/themes`, {
          signal: AbortSignal.timeout(30000),
        });
        if (!res.ok) return;
        const data = await res.json();
        setThemes(data.themes || []);
      } catch {
        /* Non-blocking. Themes appear after the first generation succeeds. */
      }
    })();
  }, []);

  async function generate() {
    const trimmed = prompt.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/generate/rough-cut`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: trimmed,
          theme: theme.trim() || undefined,
          target_duration_sec: Number(duration) || 45,
        }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.detail || `Backend error (${res.status})`);
      }
      setRoughCut(data.rough_cut);
      setThemes((prev) => {
        const nextTheme = data.theme;
        if (!nextTheme?.id) return prev;
        return [nextTheme, ...prev.filter((item) => item.id !== nextTheme.id)].slice(0, 8);
      });
    } catch (err) {
      setError(err instanceof Error ? friendlyError(err.message) : "Could not generate rough cut.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box px={3} py={3} borderBottom="1px solid" borderColor="gray.200">
      <HStack justify="space-between" mb={2}>
        <HStack gap={2}>
          <Clapperboard size={16} />
          <Text fontSize="sm" fontWeight="bold">Generate</Text>
        </HStack>
        <Badge size="sm" colorPalette="purple" variant="subtle">Rodeo style</Badge>
      </HStack>

      <VStack align="stretch" gap={2}>
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          fontSize="xs"
          placeholder="Describe the story, audience, tone, and must-have moments."
        />
        <HStack>
          <Input
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            size="sm"
            fontSize="xs"
            placeholder="Theme name"
          />
          <Input
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            size="sm"
            fontSize="xs"
            w="72px"
            inputMode="numeric"
            placeholder="Sec"
          />
        </HStack>
        <Button size="sm" colorPalette="purple" onClick={generate} disabled={loading || !prompt.trim()}>
          {loading ? <Spinner size="xs" /> : <Sparkles size={14} />}
          Generate Rough Cut
        </Button>

        {themes.length > 0 && (
          <Flex gap={1} wrap="wrap">
            {themes.slice(0, 4).map((item) => (
              <Button
                key={item.id}
                size="xs"
                variant="outline"
                onClick={() => {
                  setTheme(item.name);
                  if (item.prompt) setPrompt(item.prompt);
                }}
              >
                {item.name}
              </Button>
            ))}
          </Flex>
        )}

        {error && (
          <Text fontSize="xs" color="red.500">{error}</Text>
        )}

        {roughCut && (
          <Box mt={1} p={2} bg="purple.50" borderWidth="1px" borderColor="purple.100" borderRadius="md">
            <Text fontSize="sm" fontWeight="bold">{roughCut.title}</Text>
            <Text fontSize="xs" color="gray.700" mt={1}>{roughCut.storyline}</Text>

            {roughCut.rendered_video?.url && (
              <Box mt={2}>
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <video
                  src={artifactUrl(roughCut.rendered_video.url)}
                  controls
                  style={{ width: "100%", borderRadius: 6, background: "black" }}
                />
                <Button
                  asChild
                  size="xs"
                  variant="outline"
                  mt={2}
                >
                  <a href={artifactUrl(roughCut.rendered_video.url)} download>
                    Download MP4
                  </a>
                </Button>
              </Box>
            )}

            {roughCut.render_error && (
              <Text fontSize="xs" color="orange.600" mt={2}>
                Render not available: {friendlyError(roughCut.render_error)}
              </Text>
            )}

            {roughCut.theme_dna && roughCut.theme_dna.length > 0 && (
              <HStack gap={1} mt={2} flexWrap="wrap">
                {roughCut.theme_dna.slice(0, 3).map((item) => (
                  <Badge key={item} size="xs" colorPalette="purple" variant="subtle">{item}</Badge>
                ))}
              </HStack>
            )}

            <VStack align="stretch" gap={1.5} mt={2}>
              {(roughCut.scenes || []).slice(0, 5).map((scene) => (
                <Box key={`${scene.order}-${scene.title}`} p={2} bg="white" borderRadius="sm" borderWidth="1px" borderColor="purple.100">
                  <HStack justify="space-between" mb={1}>
                    <Text fontSize="xs" fontWeight="bold">{scene.order}. {scene.title}</Text>
                    <Badge size="xs" variant="outline">{fmt(scene.start_sec)}-{fmt(scene.end_sec)}</Badge>
                  </HStack>
                  {scene.source_video && (
                    <Text fontSize="xs" color="purple.700">{scene.source_video}</Text>
                  )}
                  <Text fontSize="xs" color="gray.700" mt={1}>{scene.purpose}</Text>
                  {scene.voiceover && (
                    <Text fontSize="xs" color="gray.600" mt={1}>VO: {scene.voiceover}</Text>
                  )}
                </Box>
              ))}
            </VStack>
          </Box>
        )}
      </VStack>
    </Box>
  );
}
