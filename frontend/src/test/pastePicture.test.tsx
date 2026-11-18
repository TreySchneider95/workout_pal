import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PastePicture } from "@/components/PastePicture";
import { pictureFile } from "@/lib/pasteImage";

const toastError = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({ toast: { error: toastError } }));

const png = () => new File([new Uint8Array([137, 80, 78, 71])], "image.png", { type: "image/png" });

const clipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  toastError.mockClear();
  if (clipboard) Object.defineProperty(navigator, "clipboard", clipboard);
  else delete (navigator as { clipboard?: unknown }).clipboard;
});

describe("PastePicture", () => {
  it("opens a paste box over plain http and uploads a pasted picture", async () => {
    vi.stubGlobal("isSecureContext", false);
    const onPicture = vi.fn();
    render(<PastePicture name="ex0033" onPicture={onPicture} />);

    await userEvent.click(screen.getByRole("button", { name: /paste picture/i }));
    const box = screen.getByRole("textbox", { name: /paste the picture here/i });

    fireEvent.paste(box, { clipboardData: { files: [png()], items: [] } });
    await waitFor(() => expect(onPicture).toHaveBeenCalledOnce());
    const file = onPicture.mock.calls[0][0] as File;
    expect(file.name).toBe("ex0033.png");
    expect(file.type).toBe("image/png");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument(); // closes after use
  });

  it("explains when what was pasted isn't a picture", async () => {
    vi.stubGlobal("isSecureContext", false);
    const onPicture = vi.fn();
    render(<PastePicture onPicture={onPicture} />);
    await userEvent.click(screen.getByRole("button", { name: /paste picture/i }));

    fireEvent.paste(screen.getByRole("textbox"), { clipboardData: { files: [], items: [] } });
    await waitFor(() => expect(toastError).toHaveBeenCalledWith(expect.stringMatching(/no picture on the clipboard/i)));
    expect(onPicture).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox")).toBeInTheDocument(); // still open to try again
  });

  it("reads the clipboard directly when the browser allows it", async () => {
    vi.stubGlobal("isSecureContext", true);
    const read = vi.fn().mockResolvedValue([{ types: ["text/plain", "image/png"], getType: async () => png() }]);
    Object.defineProperty(navigator, "clipboard", { value: { read }, configurable: true });
    const onPicture = vi.fn();
    render(<PastePicture onPicture={onPicture} />);

    await userEvent.click(screen.getByRole("button", { name: /paste picture/i }));
    await waitFor(() => expect(onPicture).toHaveBeenCalledOnce());
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument(); // no paste box needed
  });
});

describe("pictureFile", () => {
  it("names files by type and rejects non-pictures", async () => {
    const jpeg = await pictureFile(new Blob(["x"], { type: "image/jpeg" }), "ex0001");
    expect(jpeg?.name).toBe("ex0001.jpg");
    expect(await pictureFile(new Blob(["hello"], { type: "text/plain" }))).toBeNull();
  });

  it("scales big photos in other formats down so they fit the upload limit", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 4000, height: 3000 }));
    const drawn: number[][] = [];
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      fillRect: () => {},
      drawImage: (_: unknown, ...args: number[]) => drawn.push(args),
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (this: HTMLCanvasElement, done, type) {
      done(new Blob([new Uint8Array(1000)], { type: type ?? "image/png" }));
    });

    const file = await pictureFile(new Blob(["heic"], { type: "image/heic" }), "ex0002");
    expect(file?.name).toBe("ex0002.png");
    expect(drawn[0]).toEqual([0, 0, 2400, 1800]);
  });

  it("gives up (rather than failing the upload) when a picture can't be opened", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn().mockRejectedValue(new Error("unsupported")));
    expect(await pictureFile(new Blob(["avif"], { type: "image/avif" }))).toBeNull();
  });
});
