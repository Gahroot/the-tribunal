"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Trash2, BookOpen, FileText } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import * as z from "zod";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { knowledgeDocumentsApi } from "@/lib/api/knowledge-documents";
import { queryKeys } from "@/lib/query-keys";
import { formatRelative } from "@/lib/utils/date";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { formatNumber } from "@/lib/utils/number";
import type { KnowledgeDocumentCreate } from "@/types/knowledge-document";

const DOC_TYPES = [
  { value: "general", label: "General" },
  { value: "faq", label: "FAQ" },
  { value: "policy", label: "Policy" },
  { value: "script", label: "Script" },
  { value: "product", label: "Product Info" },
  { value: "persona", label: "Persona" },
] as const;

const docFormSchema = z.object({
  title: z.string().min(1, { error: "Title is required" }).max(255),
  content: z.string().trim().min(1, { error: "Content is required" }),
  doc_type: z.enum(["general", "faq", "policy", "script", "product", "persona"]),
  priority: z
    .number()
    .int()
    .min(0, { error: "Priority must be at least 0" })
    .max(100, { error: "Priority must be at most 100" }),
});

type DocFormValues = z.infer<typeof docFormSchema>;

const defaultDocValues: DocFormValues = {
  title: "",
  content: "",
  doc_type: "general",
  priority: 0,
};

interface KnowledgeBaseTabProps {
  agentId: string;
}

export function KnowledgeBaseTab({ agentId }: KnowledgeBaseTabProps) {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  const [showAddDialog, setShowAddDialog] = useState(false);

  const form = useForm<DocFormValues>({
    resolver: zodResolver(docFormSchema),
    defaultValues: defaultDocValues,
  });

  const {
    data: docList,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: queryKeys.agents.knowledgeDocs(workspaceId ?? "", agentId),
    queryFn: () => {
      if (!workspaceId) throw new Error("No workspace");
      return knowledgeDocumentsApi.list(workspaceId, agentId);
    },
    enabled: !!workspaceId,
  });

  const createMutation = useMutation({
    mutationFn: (data: KnowledgeDocumentCreate) => {
      if (!workspaceId) throw new Error("No workspace");
      return knowledgeDocumentsApi.create(workspaceId, agentId, data);
    },
    onSuccess: (doc) => {
      toast.success(
        doc.retrieval_ready
          ? "Document ready for voice and text answers"
          : "Document saved but not ready for search",
      );
      void queryClient.invalidateQueries({
        queryKey: queryKeys.agents.knowledgeDocs(workspaceId ?? "", agentId),
      });
      closeDialog();
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to add document")),
  });

  const retryMutation = useMutation({
    mutationFn: (doc: { id: string; content: string }) => {
      if (!workspaceId) throw new Error("No workspace");
      return knowledgeDocumentsApi.update(workspaceId, agentId, doc.id, { content: doc.content });
    },
    onSuccess: (doc) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.agents.knowledgeDocs(workspaceId ?? "", agentId),
      });
      if (doc.retrieval_ready) toast.success("Document ready for answers");
      else toast.error("No searchable content. Add a document with readable text.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (documentId: string) => {
      if (!workspaceId) throw new Error("No workspace");
      return knowledgeDocumentsApi.remove(workspaceId, agentId, documentId);
    },
    onSuccess: () => {
      toast.success("Document deleted");
      void queryClient.invalidateQueries({
        queryKey: queryKeys.agents.knowledgeDocs(workspaceId ?? "", agentId),
      });
    },
    onError: (err: unknown) => toast.error(getApiErrorMessage(err, "Failed to delete document")),
  });

  const closeDialog = () => {
    setShowAddDialog(false);
    form.reset(defaultDocValues);
    createMutation.reset();
  };

  const handleCreate = (data: DocFormValues) => {
    createMutation.mutate({
      title: data.title,
      content: data.content,
      doc_type: data.doc_type,
      priority: data.priority,
    });
  };

  if (isPending) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError) {
    return (
      <div role="alert" className="space-y-3 py-6">
        <p>Could not load knowledge documents. Check your connection and retry.</p>
        <Button variant="outline" onClick={() => void refetch()}>
          Retry loading
        </Button>
      </div>
    );
  }

  const totalTokens = docList?.total_tokens ?? 0;

  return (
    <div className="space-y-6">
      {/* Knowledge readiness */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Knowledge Base</CardTitle>
              <CardDescription>
                Ready documents are searched automatically for voice and text answers. No tool
                setting is needed.
              </CardDescription>
            </div>
            <Button onClick={() => setShowAddDialog(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Document
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Active reference text</span>
            <span className="font-medium">{formatNumber(totalTokens)} tokens</span>
          </div>
        </CardContent>
      </Card>

      {/* Document List */}
      {!docList?.items.length ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <BookOpen className="mb-4 h-12 w-12 text-muted-foreground" />
            <h3 className="mb-2 text-lg font-semibold">No Documents</h3>
            <p className="max-w-sm text-sm text-muted-foreground">
              Add documents to give your agent knowledge about your business, products, and
              processes.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {docList.items.map((doc) => (
            <Card key={doc.id}>
              <CardContent className="flex items-start gap-4 p-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-medium leading-tight">{doc.title}</h3>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <Badge variant="outline" className="text-xs">
                        {doc.doc_type}
                      </Badge>
                      <Badge variant="outline" className="text-xs">
                        {formatNumber(doc.token_count)} tokens
                      </Badge>
                      {doc.priority > 0 && (
                        <Badge variant="secondary" className="text-xs">
                          Priority: {doc.priority}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <Badge variant="outline" className="text-xs">
                    {!doc.is_active
                      ? "Inactive"
                      : doc.retrieval_ready
                        ? "Ready for answers"
                        : "Not indexed"}
                  </Badge>
                  {doc.is_active && !doc.retrieval_ready && (
                    <div className="space-y-2 text-sm">
                      <p>
                        This document is not searchable yet. Retry indexing before testing voice
                        answers.
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={retryMutation.isPending}
                        onClick={() => retryMutation.mutate(doc)}
                      >
                        {retryMutation.isPending && retryMutation.variables?.id === doc.id
                          ? "Indexing..."
                          : "Retry indexing"}
                      </Button>
                      {retryMutation.isError && retryMutation.variables?.id === doc.id && (
                        <p role="alert">
                          {getApiErrorMessage(
                            retryMutation.error,
                            "Indexing failed. Check the document text and retry.",
                          )}
                        </p>
                      )}
                    </div>
                  )}
                  <p className="line-clamp-2 text-sm text-muted-foreground">{doc.content}</p>
                  <p className="text-xs text-muted-foreground">
                    Added {formatRelative(doc.created_at)}
                  </p>
                </div>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                      aria-label={`Delete ${doc.title}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete document?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will permanently remove &ldquo;{doc.title}&rdquo; from the knowledge
                        base.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => deleteMutation.mutate(doc.id)}
                        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                      >
                        Delete
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Add Document Dialog */}
      <Dialog
        open={showAddDialog}
        onOpenChange={(open) => {
          if (!open) closeDialog();
          else setShowAddDialog(true);
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Add Knowledge Document</DialogTitle>
            <DialogDescription>
              Add a document to your agent&apos;s knowledge base. This content will be available
              during conversations.
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleCreate)} className="space-y-4">
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Title</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. Company FAQ" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="doc_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Document Type</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {DOC_TYPES.map((dt) => (
                            <SelectItem key={dt.value} value={dt.value}>
                              {dt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="priority"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Priority (0 = default)</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={0}
                          max={100}
                          value={field.value}
                          onChange={(e) => {
                            const val = parseInt(e.target.value, 10);
                            field.onChange(isNaN(val) ? 0 : val);
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <FormField
                control={form.control}
                name="content"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Content</FormLabel>
                    <FormControl>
                      <Textarea placeholder="Enter the document content..." rows={10} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {createMutation.isError && (
                <p role="alert" className="text-sm text-destructive">
                  {getApiErrorMessage(
                    createMutation.error,
                    "Indexing failed. Check the document text and retry.",
                  )}{" "}
                  The document was not added. Your text is still here; retry saving.
                </p>
              )}
              <DialogFooter>
                <Button type="button" variant="outline" onClick={closeDialog}>
                  Cancel
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Indexing...
                    </>
                  ) : (
                    "Add Document"
                  )}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
