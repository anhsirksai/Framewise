"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Badge,
  Box,
  Button,
  Flex,
  Heading,
  HStack,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import { CheckCircle2, CircleAlert, CloudUpload, FileVideo, SkipForward } from "lucide-react";
import { API_BASE } from "@/lib/config";
import { friendlyError } from "@/lib/errors";

interface IngestJob {
  id: string;
  filename: string;
  status: "running" | "completed" | "skipped" | "failed";
  stage: string;
  detail: string;
  video_id: string | null;
  title: string | null;
  error: string | null;
  created_at: number;
  updated_at: number;
}

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  checking: "Checking for duplicates",
  transcoding: "Downscaling to 2160p",
  indexing: "Indexing with TwelveLabs",
  analyzing: "Analyzing (Pegasus)",
  structuring: "Extracting segments (LLM)",
  embedding: "Embedding segments",
  writing: "Writing to graph",
  done: "Done",
  error: "Error",
};

const STAGE_ORDER = ["checking", "transcoding", "indexing", "analyzing", "structuring", "embedding", "writing"];

function StatusBadge({ job }: { job: IngestJob }) {
  if (job.status === "running") {
    return (
      <Badge colorPalette="blue" display="inline-flex" alignItems="center" gap={1}>
        <Spinner size="xs" /> {STAGE_LABELS[job.stage] ?? job.stage}
      </Badge>
    );
  }
  if (job.status === "completed") {
    return (
      <Badge colorPalette="green" display="inline-flex" alignItems="center" gap={1}>
        <CheckCircle2 size={12} /> Ingested
      </Badge>
    );
  }
  if (job.status === "skipped") {
    return (
      <Badge colorPalette="gray" display="inline-flex" alignItems="center" gap={1}>
        <SkipForward size={12} /> Duplicate — skipped
      </Badge>
    );
  }
  return (
    <Badge colorPalette="red" display="inline-flex" alignItems="center" gap={1}>
      <CircleAlert size={12} /> Failed
    </Badge>
  );
}

function StageProgress({ job }: { job: IngestJob }) {
  if (job.status !== "running") return null;
  const currentIdx = STAGE_ORDER.indexOf(job.stage);
  return (
    <HStack gap={1} mt={2}>
      {STAGE_ORDER.map((stage, i) => (
        <Box
          key={stage}
          flex={1}
          h="4px"
          borderRadius="full"
          bg={i < currentIdx ? "green.400" : i === currentIdx ? "blue.400" : "gray.200"}
          title={STAGE_LABELS[stage]}
        />
      ))}
    </HStack>
  );
}

export function IngestView({ onIngested }: { onIngested?: () => void }) {
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hasRunning = jobs.some((j) => j.status === "running");
  const notifiedJobs = useRef<Set<string>>(new Set());

  const refreshJobs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/ingest/jobs`, { signal: AbortSignal.timeout(30000) });
      if (!res.ok) return;
      const data = await res.json();
      setJobs(data.jobs ?? []);
      for (const j of data.jobs ?? []) {
        if (j.status === "completed" && !notifiedJobs.current.has(j.id)) {
          notifiedJobs.current.add(j.id);
          onIngested?.();
        }
      }
    } catch {
      /* transient poll failure — next tick will retry */
    }
  }, [onIngested]);

  // Poll fast while a job is running, slowly otherwise.
  useEffect(() => {
    refreshJobs();
    const interval = setInterval(refreshJobs, hasRunning ? 2500 : 15000);
    return () => clearInterval(interval);
  }, [refreshJobs, hasRunning]);

  const upload = useCallback(
    async (file: File) => {
      setError(null);
      setUploading(true);
      try {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch(`${API_BASE}/ingest/upload`, { method: "POST", body: form });
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail ?? `Upload failed (HTTP ${res.status})`);
        }
        await refreshJobs();
      } catch (e) {
        setError(e instanceof Error ? friendlyError(e.message) : "Upload failed.");
      } finally {
        setUploading(false);
      }
    },
    [refreshJobs],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) upload(file);
    },
    [upload],
  );

  return (
    <Box maxW="720px" mx="auto" px={6} py={8} h="100%" overflow="auto">
      <Heading size="md" mb={1}>
        Ingest a video
      </Heading>
      <Text fontSize="sm" color="gray.500" mb={6}>
        Upload a video and Framewise will index it with TwelveLabs, extract segments, entities and
        topics, and add it to the evidence graph. Duplicates are detected and skipped automatically.
      </Text>

      {/* Drop zone */}
      <Flex
        direction="column"
        align="center"
        justify="center"
        gap={3}
        py={12}
        px={6}
        borderWidth="2px"
        borderStyle="dashed"
        borderColor={dragOver ? "blue.400" : "gray.300"}
        borderRadius="lg"
        bg={dragOver ? "blue.50" : "gray.50"}
        transition="all 0.15s"
        cursor="pointer"
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <CloudUpload size={36} color="var(--chakra-colors-gray-400)" />
        <Text fontWeight="medium">{uploading ? "Uploading…" : "Drop a video here or click to browse"}</Text>
        <Text fontSize="xs" color="gray.500">
          .mp4, .mov, .webm, .mkv, .avi — up to 2GB. Indexing takes a few minutes.
        </Text>
        {uploading && <Spinner size="sm" />}
        <input
          ref={fileInputRef}
          type="file"
          accept="video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload(file);
            e.target.value = "";
          }}
        />
      </Flex>

      {error && (
        <Text mt={3} fontSize="sm" color="red.500">
          {error}
        </Text>
      )}

      {/* Job list */}
      {jobs.length > 0 && (
        <Box mt={8}>
          <Heading size="sm" mb={3}>
            Ingestion jobs
          </Heading>
          <VStack align="stretch" gap={3}>
            {jobs.map((job) => (
              <Box key={job.id} borderWidth="1px" borderColor="gray.200" borderRadius="md" p={4}>
                <Flex justify="space-between" align="center" gap={3}>
                  <HStack gap={2} minW={0}>
                    <FileVideo size={16} />
                    <Text fontWeight="medium" fontSize="sm" truncate title={job.filename}>
                      {job.filename}
                    </Text>
                  </HStack>
                  <StatusBadge job={job} />
                </Flex>
                <StageProgress job={job} />
                <Text mt={2} fontSize="xs" color={job.status === "failed" ? "red.500" : "gray.500"}>
                  {job.status === "failed" ? friendlyError(job.error) : job.detail}
                </Text>
              </Box>
            ))}
          </VStack>
        </Box>
      )}

      {jobs.length === 0 && (
        <Flex mt={8} align="center" gap={2} color="gray.400">
          <Text fontSize="sm">No ingestion jobs yet — upload your first video above.</Text>
        </Flex>
      )}

      <Box mt={8} p={4} bg="blue.50" borderRadius="md">
        <Text fontSize="xs" color="blue.800">
          <b>Pipeline:</b> TwelveLabs (Marengo + Pegasus) indexes and describes the video → the LLM
          structures it into segments, entities and topics → Marengo embeds each segment → everything
          lands in the Neo4j evidence graph. Once a job shows <b>Ingested</b>, switch to Explore and
          ask questions about it.
        </Text>
      </Box>
    </Box>
  );
}
