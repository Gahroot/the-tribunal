"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Search,
  Phone,
  Globe,
  Star,
  MapPin,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Users,
  Sparkles,
  Linkedin,
  Clock,
  XCircle,
} from "lucide-react";

import {
  findLeadsAIApi,
  type BusinessResult,
  type AIImportLeadsResponse,
} from "@/lib/api/find-leads-ai";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Filters {
  hasPhone: boolean;
  hasWebsite: boolean;
  minRating: number | null;
}

export function FindLeadsAIPage() {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<BusinessResult[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<Filters>({
    hasPhone: true,
    hasWebsite: true,
    minRating: null,
  });
  const [defaultStatus, setDefaultStatus] = useState("new");
  const [enableEnrichment, setEnableEnrichment] = useState(true);
  const [importResult, setImportResult] = useState<AIImportLeadsResponse | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const searchMutation = useMutation({
    mutationFn: async () => {
      if (!workspaceId) throw new Error("No workspace");
      return findLeadsAIApi.search(workspaceId, query, 40);
    },
    onSuccess: (data) => {
      setResults(data.results);
      setHasSearched(true);
      setImportResult(null);
      // Auto-select businesses with phone AND website (enrichable)
      const withPhoneAndWebsite = new Set(
        data.results
          .filter((r) => r.has_phone && r.has_website)
          .map((r) => r.place_id)
      );
      setSelectedIds(withPhoneAndWebsite);
      toast.success(`Found ${data.results.length} businesses`);
    },
    onError: (error) => {
      console.error("Search failed:", error);
      toast.error("Failed to search. Please check your API key configuration.");
    },
  });

  const importMutation = useMutation({
    mutationFn: async () => {
      if (!workspaceId) throw new Error("No workspace");
      const selectedLeads = results.filter((r) => selectedIds.has(r.place_id));
      return findLeadsAIApi.importLeads(workspaceId, {
        leads: selectedLeads,
        default_status: defaultStatus,
        enable_enrichment: enableEnrichment,
      });
    },
    onSuccess: (data) => {
      setImportResult(data);
      queryClient.invalidateQueries({ queryKey: ["contacts", workspaceId] });
      if (data.imported > 0) {
        const enrichMsg = data.queued_for_enrichment > 0
          ? ` (${data.queued_for_enrichment} queued for AI enrichment)`
          : "";
        toast.success(`Successfully imported ${data.imported} leads${enrichMsg}`);
      }
    },
    onError: (error) => {
      console.error("Import failed:", error);
      toast.error("Failed to import leads");
    },
  });

  const handleSearch = () => {
    if (!query.trim()) {
      toast.error("Please enter a search query");
      return;
    }
    searchMutation.mutate();
  };

  const handleImport = () => {
    if (selectedIds.size === 0) {
      toast.error("Please select at least one lead to import");
      return;
    }
    importMutation.mutate();
  };

  const toggleSelect = (placeId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(placeId)) {
        next.delete(placeId);
      } else {
        next.add(placeId);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    const filtered = filteredResults;
    const allSelected = filtered.every((r) => selectedIds.has(r.place_id));
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filtered.map((r) => r.place_id)));
    }
  };

  const filteredResults = results.filter((r) => {
    if (filters.hasPhone && !r.has_phone) return false;
    if (filters.hasWebsite && !r.has_website) return false;
    if (filters.minRating && (!r.rating || r.rating < filters.minRating)) return false;
    return true;
  });

  const selectedCount = [...selectedIds].filter((id) =>
    filteredResults.some((r) => r.place_id === id)
  ).length;

  const enrichableCount = [...selectedIds].filter((id) => {
    const result = filteredResults.find((r) => r.place_id === id);
    return result?.has_website;
  }).length;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="shrink-0 p-6 border-b space-y-4">
        <div className="flex items-center gap-3">
          <Sparkles className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Find Leads AI</h1>
            <p className="text-sm text-muted-foreground">
              AI-powered lead enrichment with social media discovery
            </p>
          </div>
        </div>

        {/* Search Bar */}
        <div className="flex gap-2 max-w-2xl">
          <Input
            placeholder="e.g., plumbers in Austin TX, restaurants in downtown Seattle"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="flex-1"
          />
          <Button
            onClick={handleSearch}
            disabled={searchMutation.isPending || !query.trim()}
            className="gap-2"
          >
            {searchMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            Search
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {!hasSearched ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-6">
            <Sparkles className="h-16 w-16 text-muted-foreground/50 mb-4" />
            <h3 className="text-lg font-medium mb-2">AI-Enhanced Lead Discovery</h3>
            <p className="text-sm text-muted-foreground max-w-md mb-4">
              Search for businesses and we&apos;ll automatically enrich them with social media
              profiles (LinkedIn, Facebook, etc.) for personalized AI messaging.
            </p>
            <div className="flex flex-wrap gap-2 justify-center text-xs text-muted-foreground">
              <Badge variant="outline" className="gap-1">
                <Linkedin className="h-3 w-3" /> LinkedIn Discovery
              </Badge>
              <Badge variant="outline" className="gap-1">
                <Globe className="h-3 w-3" /> Website Scraping
              </Badge>
              <Badge variant="outline" className="gap-1">
                <Sparkles className="h-3 w-3" /> AI Personalization
              </Badge>
            </div>
          </div>
        ) : (
          <div className="flex flex-col h-full p-6 gap-4">
            {/* Import Result Banner */}
            {importResult && (
              <Card className="border-green-500/50 bg-green-500/5">
                <CardContent className="p-4">
                  <div className="flex items-center gap-4">
                    <CheckCircle2 className="h-8 w-8 text-green-500" />
                    <div className="flex-1">
                      <p className="font-medium">
                        Successfully imported {importResult.imported} leads
                      </p>
                      <div className="flex gap-4 text-sm text-muted-foreground">
                        {importResult.queued_for_enrichment > 0 && (
                          <span className="flex items-center gap-1">
                            <Sparkles className="h-3 w-3" />
                            {importResult.queued_for_enrichment} queued for AI enrichment
                          </span>
                        )}
                        {importResult.skipped_duplicates > 0 && (
                          <span>{importResult.skipped_duplicates} duplicates skipped</span>
                        )}
                        {importResult.skipped_no_phone > 0 && (
                          <span>{importResult.skipped_no_phone} skipped (no phone)</span>
                        )}
                      </div>
                    </div>
                    <Button variant="outline" size="sm" asChild>
                      <Link href="/">View Contacts</Link>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Filters & Actions */}
            <div className="flex flex-wrap items-center gap-4 p-3 bg-muted/50 rounded-lg">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="filter-phone"
                  checked={filters.hasPhone}
                  onCheckedChange={(checked) =>
                    setFilters({ ...filters, hasPhone: checked === true })
                  }
                />
                <Label htmlFor="filter-phone" className="text-sm cursor-pointer">
                  Has phone
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="filter-website"
                  checked={filters.hasWebsite}
                  onCheckedChange={(checked) =>
                    setFilters({ ...filters, hasWebsite: checked === true })
                  }
                />
                <Label htmlFor="filter-website" className="text-sm cursor-pointer flex items-center gap-1">
                  Has website
                  <Badge variant="secondary" className="text-[10px] px-1 py-0">
                    AI
                  </Badge>
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Label className="text-sm">Min rating:</Label>
                <Select
                  value={filters.minRating?.toString() || "any"}
                  onValueChange={(v) =>
                    setFilters({ ...filters, minRating: v === "any" ? null : parseFloat(v) })
                  }
                >
                  <SelectTrigger className="w-20 h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any</SelectItem>
                    <SelectItem value="3">3+</SelectItem>
                    <SelectItem value="4">4+</SelectItem>
                    <SelectItem value="4.5">4.5+</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex-1" />
              <span className="text-sm text-muted-foreground">
                {filteredResults.length} of {results.length} shown
              </span>
            </div>

            {/* Selection bar */}
            <div className="flex items-center gap-3">
              <Checkbox
                checked={filteredResults.length > 0 && filteredResults.every((r) => selectedIds.has(r.place_id))}
                onCheckedChange={toggleSelectAll}
              />
              <span className="text-sm font-medium">{selectedCount} selected</span>
              {enableEnrichment && enrichableCount > 0 && (
                <Badge variant="secondary" className="gap-1">
                  <Sparkles className="h-3 w-3" />
                  {enrichableCount} enrichable
                </Badge>
              )}
              <div className="flex-1" />
              <div className="flex items-center gap-2">
                <Checkbox
                  id="enable-enrichment"
                  checked={enableEnrichment}
                  onCheckedChange={(checked) => setEnableEnrichment(checked === true)}
                />
                <Label htmlFor="enable-enrichment" className="text-sm cursor-pointer">
                  AI Enrichment
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Label className="text-sm">Import as:</Label>
                <Select value={defaultStatus} onValueChange={setDefaultStatus}>
                  <SelectTrigger className="w-28 h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="new">New</SelectItem>
                    <SelectItem value="contacted">Contacted</SelectItem>
                    <SelectItem value="qualified">Qualified</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button
                onClick={handleImport}
                disabled={selectedCount === 0 || importMutation.isPending}
                className="gap-2"
              >
                {importMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Users className="h-4 w-4" />
                )}
                Import {selectedCount} Lead{selectedCount !== 1 ? "s" : ""}
              </Button>
            </div>

            {/* Results Grid */}
            <ScrollArea className="flex-1 min-h-0">
              {filteredResults.length === 0 ? (
                <div className="py-16 text-center text-muted-foreground">
                  <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>No results match your filters</p>
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 pr-4">
                  {filteredResults.map((result) => (
                    <Card
                      key={result.place_id}
                      className={cn(
                        "cursor-pointer transition-all",
                        selectedIds.has(result.place_id)
                          ? "ring-2 ring-primary border-primary"
                          : "hover:border-primary/50"
                      )}
                      onClick={() => toggleSelect(result.place_id)}
                    >
                      <CardHeader className="p-4 pb-2">
                        <div className="flex items-start gap-3">
                          <Checkbox
                            checked={selectedIds.has(result.place_id)}
                            onCheckedChange={() => toggleSelect(result.place_id)}
                            className="mt-1"
                            onClick={(e) => e.stopPropagation()}
                          />
                          <div className="flex-1 min-w-0">
                            <CardTitle className="text-base truncate">
                              {result.name}
                            </CardTitle>
                            {result.rating && (
                              <div className="flex items-center gap-1 mt-1">
                                <Star className="h-3 w-3 fill-yellow-500 text-yellow-500" />
                                <span className="text-sm">{result.rating}</span>
                                {result.review_count > 0 && (
                                  <span className="text-xs text-muted-foreground">
                                    ({result.review_count})
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                          {/* Enrichment indicator */}
                          {result.has_website && enableEnrichment && (
                            <Badge variant="secondary" className="shrink-0 gap-1 text-xs">
                              <Sparkles className="h-3 w-3" />
                              AI
                            </Badge>
                          )}
                        </div>
                      </CardHeader>
                      <CardContent className="p-4 pt-0">
                        {result.address && (
                          <CardDescription className="flex items-start gap-1 mb-2">
                            <MapPin className="h-3 w-3 mt-0.5 shrink-0" />
                            <span className="line-clamp-2">{result.address}</span>
                          </CardDescription>
                        )}
                        <div className="flex items-center gap-4 text-sm">
                          <div
                            className={cn(
                              "flex items-center gap-1",
                              result.has_phone ? "text-green-600" : "text-muted-foreground"
                            )}
                          >
                            <Phone className="h-3 w-3" />
                            <span className="truncate max-w-[120px]">
                              {result.phone_number || "No phone"}
                            </span>
                          </div>
                          <div
                            className={cn(
                              "flex items-center gap-1",
                              result.has_website ? "text-blue-600" : "text-muted-foreground"
                            )}
                          >
                            <Globe className="h-3 w-3" />
                            {result.has_website ? "Website" : "None"}
                          </div>
                        </div>
                        {result.types.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {result.types.slice(0, 2).map((type) => (
                              <Badge key={type} variant="outline" className="text-xs">
                                {type.replace(/_/g, " ")}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>
        )}
      </div>
    </div>
  );
}

// Enrichment status badge component for contact cards (can be used elsewhere)
export function EnrichmentStatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return null;

  const statusConfig = {
    pending: { icon: Clock, label: "Enriching...", className: "text-yellow-600 bg-yellow-50" },
    enriched: { icon: CheckCircle2, label: "Enriched", className: "text-green-600 bg-green-50" },
    failed: { icon: XCircle, label: "Failed", className: "text-red-600 bg-red-50" },
    skipped: { icon: null, label: "No website", className: "text-muted-foreground bg-muted" },
  };

  const config = statusConfig[status as keyof typeof statusConfig];
  if (!config) return null;

  const Icon = config.icon;

  return (
    <Badge variant="outline" className={cn("gap-1 text-xs", config.className)}>
      {Icon && <Icon className="h-3 w-3" />}
      {config.label}
    </Badge>
  );
}
