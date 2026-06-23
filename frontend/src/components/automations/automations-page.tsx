"use client";

import { Plus, Search, Zap } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageEmptyState, PageErrorState } from "@/components/ui/page-state";

import { AutomationCard, AutomationCardSkeleton } from "./automation-card";
import { containerVariants } from "./automation-config";
import { AutomationFormDialog } from "./automation-form-dialog";
import { AutomationStats } from "./automation-stats";
import { useAutomationsController } from "./use-automations-controller";

export function AutomationsPage() {
  const {
    searchQuery,
    setSearchQuery,
    automations,
    filteredAutomations,
    activeCount,
    triggeredToday,
    isPending,
    error,
    isDialogOpen,
    isEditing,
    form,
    updateForm,
    onDialogOpenChange,
    openCreateDialog,
    openConfigureDialog,
    submitForm,
    isSubmitting,
    toggleAutomation,
    deleteAutomation,
    duplicateAutomation,
    isToggling,
    isDeleting,
    isDuplicating,
  } = useAutomationsController();

  if (error) {
    return (
      <div className="p-6">
        <PageErrorState message="Failed to load automations" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Automations</h1>
          <p className="text-muted-foreground">
            Create workflows to automate repetitive tasks
          </p>
        </div>
        <Button onClick={openCreateDialog}>
          <Plus className="mr-2 size-4" />
          Create Automation
        </Button>
        <AutomationFormDialog
          open={isDialogOpen}
          isEditing={isEditing}
          form={form}
          isSubmitting={isSubmitting}
          onFormChange={updateForm}
          onOpenChange={onDialogOpenChange}
          onSubmit={submitForm}
          onCancel={() => onDialogOpenChange(false)}
        />
      </div>

      {/* Stats */}
      <AutomationStats
        totalCount={automations.length}
        activeCount={activeCount}
        triggeredToday={triggeredToday}
        isLoading={isPending}
      />

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search automations..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Automations Grid */}
      {isPending ? (
        <div className="grid gap-4 md:grid-cols-2">
          <AutomationCardSkeleton />
          <AutomationCardSkeleton />
          <AutomationCardSkeleton />
          <AutomationCardSkeleton />
        </div>
      ) : filteredAutomations.length === 0 ? (
        <Card>
          <CardContent className="py-4">
            <PageEmptyState
              icon={<Zap className="size-12" />}
              title="No automations found"
              description={
                searchQuery
                  ? "Try adjusting your search"
                  : "Create your first automation to automate repetitive tasks"
              }
              action={
                !searchQuery ? (
                  <Button onClick={openCreateDialog}>
                    <Plus className="mr-2 size-4" />
                    Create Automation
                  </Button>
                ) : undefined
              }
            />
          </CardContent>
        </Card>
      ) : (
        <motion.div
          className="grid gap-4 md:grid-cols-2"
          variants={containerVariants}
          initial="hidden"
          animate="visible"
        >
          <AnimatePresence mode="popLayout">
            {filteredAutomations.map((automation) => (
              <AutomationCard
                key={automation.id}
                automation={automation}
                onConfigure={openConfigureDialog}
                onToggle={toggleAutomation}
                onDuplicate={duplicateAutomation}
                onDelete={deleteAutomation}
                isToggling={isToggling}
                isDuplicating={isDuplicating}
                isDeleting={isDeleting}
              />
            ))}
          </AnimatePresence>
        </motion.div>
      )}
    </div>
  );
}
