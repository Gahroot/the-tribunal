/** Stream mono microphone samples at a fixed rate across callback boundaries. */
export function createPcmResampler(inputRate: number, outputRate: number) {
  if (inputRate === outputRate) return (input: Float32Array) => input;

  const step = inputRate / outputRate;
  let previousSample: number | undefined;
  let nextPosition = 0;

  return (input: Float32Array): Float32Array => {
    if (input.length === 0) return new Float32Array(0);
    const source = new Float32Array(input.length + (previousSample === undefined ? 0 : 1));
    if (previousSample !== undefined) source[0] = previousSample;
    source.set(input, previousSample === undefined ? 0 : 1);

    const samples: number[] = [];
    while (nextPosition < source.length - 1) {
      const index = Math.floor(nextPosition);
      const fraction = nextPosition - index;
      samples.push(source[index] + (source[index + 1] - source[index]) * fraction);
      nextPosition += step;
    }
    nextPosition -= source.length - 1;
    previousSample = source[source.length - 1];
    return Float32Array.from(samples);
  };
}
