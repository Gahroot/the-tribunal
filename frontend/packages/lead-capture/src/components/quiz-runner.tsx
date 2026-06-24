"use client";

import { RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Slider } from "@/components/ui/slider";
import type { QuizContent, QuizQuestion } from "@/types";

interface QuizRunnerProps {
  content: QuizContent;
}

type Answer = string | string[] | number;

function scoreQuestion(question: QuizQuestion, answer: Answer | undefined): number {
  if (answer === undefined) return 0;

  if (question.type === "scale") {
    const value = typeof answer === "number" ? answer : 0;
    return value * (question.weight ?? 1);
  }

  if (question.type === "multiple_choice") {
    const selected = Array.isArray(answer) ? answer : [];
    return question.options
      .filter((opt) => selected.includes(opt.id))
      .reduce((sum, opt) => sum + opt.score, 0);
  }

  // single_choice
  const selectedId = typeof answer === "string" ? answer : undefined;
  return question.options.find((opt) => opt.id === selectedId)?.score ?? 0;
}

/**
 * Interactive quiz a prospect can actually take on a public page. Sums option
 * scores and maps the total to one of the configured result bands.
 */
export function QuizRunner({ content }: QuizRunnerProps) {
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [submitted, setSubmitted] = useState(false);

  const questions = useMemo(() => content.questions ?? [], [content.questions]);

  const totalScore = useMemo(
    () =>
      questions.reduce(
        (sum, question) => sum + scoreQuestion(question, answers[question.id]),
        0,
      ),
    [questions, answers],
  );

  const result = useMemo(() => {
    const results = content.results ?? [];
    return (
      results.find(
        (r) => totalScore >= r.min_score && totalScore <= r.max_score,
      ) ?? results[results.length - 1]
    );
  }, [content.results, totalScore]);

  const allAnswered = questions.every((q) => {
    const answer = answers[q.id];
    if (answer === undefined) return false;
    if (Array.isArray(answer)) return answer.length > 0;
    return true;
  });

  if (questions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        This quiz has no questions yet.
      </p>
    );
  }

  if (submitted && result) {
    return (
      <div className="space-y-3 rounded-lg border border-primary/20 bg-primary/5 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Your Result
        </p>
        <h4 className="text-lg font-semibold">{result.title}</h4>
        {result.description && (
          <p className="text-sm text-muted-foreground">{result.description}</p>
        )}
        <div className="flex flex-wrap items-center gap-3 pt-1">
          {result.cta_text && (
            <Button size="sm" type="button">
              {result.cta_text}
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            type="button"
            onClick={() => {
              setAnswers({});
              setSubmitted(false);
            }}
          >
            <RotateCcw className="size-4 mr-2" />
            Retake
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {content.description && (
        <p className="text-sm text-muted-foreground">{content.description}</p>
      )}

      {questions.map((question, index) => (
        <div key={question.id} className="space-y-3">
          <p className="text-sm font-medium">
            {index + 1}. {question.text}
          </p>

          {question.type === "single_choice" && (
            <RadioGroup
              value={(answers[question.id] as string) ?? ""}
              onValueChange={(value) =>
                setAnswers((prev) => ({ ...prev, [question.id]: value }))
              }
            >
              {question.options.map((opt) => (
                <div key={opt.id} className="flex items-center gap-2">
                  <RadioGroupItem value={opt.id} id={`${question.id}-${opt.id}`} />
                  <Label
                    htmlFor={`${question.id}-${opt.id}`}
                    className="text-sm font-normal cursor-pointer"
                  >
                    {opt.text}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          )}

          {question.type === "multiple_choice" && (
            <div className="grid gap-2">
              {question.options.map((opt) => {
                const selected = Array.isArray(answers[question.id])
                  ? (answers[question.id] as string[])
                  : [];
                return (
                  <div key={opt.id} className="flex items-center gap-2">
                    <Checkbox
                      id={`${question.id}-${opt.id}`}
                      checked={selected.includes(opt.id)}
                      onCheckedChange={(checked) =>
                        setAnswers((prev) => {
                          const current = Array.isArray(prev[question.id])
                            ? (prev[question.id] as string[])
                            : [];
                          return {
                            ...prev,
                            [question.id]:
                              checked === true
                                ? [...current, opt.id]
                                : current.filter((id) => id !== opt.id),
                          };
                        })
                      }
                    />
                    <Label
                      htmlFor={`${question.id}-${opt.id}`}
                      className="text-sm font-normal cursor-pointer"
                    >
                      {opt.text}
                    </Label>
                  </div>
                );
              })}
            </div>
          )}

          {question.type === "scale" && (
            <div className="space-y-2">
              <Slider
                min={1}
                max={10}
                step={1}
                value={[
                  typeof answers[question.id] === "number"
                    ? (answers[question.id] as number)
                    : 1,
                ]}
                onValueChange={([value]) =>
                  setAnswers((prev) => ({ ...prev, [question.id]: value }))
                }
              />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>1</span>
                <span className="font-medium text-foreground">
                  {typeof answers[question.id] === "number"
                    ? (answers[question.id] as number)
                    : 1}
                </span>
                <span>10</span>
              </div>
            </div>
          )}
        </div>
      ))}

      <Button
        type="button"
        disabled={!allAnswered}
        onClick={() => setSubmitted(true)}
      >
        See My Result
      </Button>
    </div>
  );
}
