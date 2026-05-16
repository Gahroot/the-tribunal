"use client"

import * as AvatarPrimitive from "@radix-ui/react-avatar"
import Image from "next/image"
import * as React from "react"

import { cn } from "@/lib/utils"

function Avatar({
  className,
  ...props
}: React.ComponentProps<typeof AvatarPrimitive.Root>) {
  return (
    <AvatarPrimitive.Root
      data-slot="avatar"
      className={cn(
        "relative flex size-8 shrink-0 overflow-hidden rounded-full",
        className
      )}
      {...props}
    />
  )
}

interface AvatarImageProps
  extends Omit<React.ComponentProps<typeof AvatarPrimitive.Image>, "src" | "alt"> {
  src: string | null | undefined
  alt: string
  /** Pixel size hint for next/image. Defaults to 96 (covers up to ~size-20). */
  size?: number
}

/**
 * Image slot for {@link Avatar}. Renders a next/image inside Radix's
 * `Avatar.Image` so we still get its load/error-driven fallback behaviour.
 *
 * Pass `src={null}` (or `undefined`) to skip rendering entirely — Radix will
 * then fall through to {@link AvatarFallback}.
 */
function AvatarImage({ className, src, alt, size = 96, ...props }: AvatarImageProps) {
  if (!src) return null
  return (
    <AvatarPrimitive.Image asChild {...props}>
      <Image
        data-slot="avatar-image"
        src={src}
        alt={alt}
        width={size}
        height={size}
        className={cn("aspect-square size-full object-cover", className)}
      />
    </AvatarPrimitive.Image>
  )
}

function AvatarFallback({
  className,
  ...props
}: React.ComponentProps<typeof AvatarPrimitive.Fallback>) {
  return (
    <AvatarPrimitive.Fallback
      data-slot="avatar-fallback"
      className={cn(
        "bg-muted flex size-full items-center justify-center rounded-full",
        className
      )}
      {...props}
    />
  )
}

export { Avatar, AvatarImage, AvatarFallback }
