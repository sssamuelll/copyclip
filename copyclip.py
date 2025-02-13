import os
import pyperclip
import argparse
from gitignore_parser import parse_gitignore
from multiprocessing import Pool, cpu_count, Manager, Process
from tqdm import tqdm

def read_file_content(file_path):
    """Reads the content of a file and returns it as a string."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return file_path, f.read()
    except Exception as e:
        print(f"[WARN] Error reading {file_path}: {e}")
        return file_path, None

def process_file(args):
    """Wrapper for multiprocessing pool to read file content."""
    file_path, base_path, progress_queue = args
    relative_path = os.path.relpath(file_path, base_path)
    content = read_file_content(file_path)
    # Notificamos que terminamos de leer 1 archivo
    progress_queue.put(1)
    return relative_path, content[1]

def progress_listener(total_files, queue):
    """
    Proceso que escucha las notificaciones de avance y 
    actualiza la barra de progreso con tqdm en "tiempo real".
    """
    with tqdm(total=total_files, desc="Reading files") as pbar:
        processed_count = 0
        while processed_count < total_files:
            # Esperamos que un worker nos avise que terminó un archivo
            item = queue.get()
            if item is not None:
                processed_count += 1
                pbar.update(1)

def scan_files(base_path, ignore_file_path=None, extension=None):
    """
    Escanea todo el árbol de directorios en base_path y devuelve
    una lista con las rutas absolutas de los archivos que se quieran procesar.
    """
    # Prepara la función is_ignored
    if ignore_file_path and os.path.exists(ignore_file_path):
        is_ignored = parse_gitignore(ignore_file_path, base_dir=base_path)
    else:
        is_ignored = lambda x: False

    # Primero, contamos cuántos archivos hay en total
    # para poder mostrar una barra de scanning
    print("[INFO] Scanning directory tree...")
    total_files_in_tree = 0
    for root, dirs, files_in_dir in os.walk(base_path):
        total_files_in_tree += len(files_in_dir)

    # Ahora hacemos la segunda pasada con una barra de progreso
    all_files = []
    with tqdm(total=total_files_in_tree, desc="Scanning files") as scan_bar:
        for root, dirs, files_in_dir in os.walk(base_path):
            for file_name in files_in_dir:
                scan_bar.update(1)  # Cada archivo escaneado (aunque luego lo ignoremos)

                absolute_file_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(absolute_file_path, base_path)

                # Aplicamos .copyclipignore y extensión (si se definió)
                if is_ignored(relative_path):
                    continue
                if extension and not file_name.endswith(extension):
                    continue

                all_files.append(absolute_file_path)
    return all_files

def get_files_with_content(all_files, base_path):
    """
    Usa multiprocessing para leer los archivos de all_files en paralelo.
    Devuelve {relative_path: file_content}.
    """
    files_with_content = {}

    # Manager para la cola de progreso
    manager = Manager()
    progress_queue = manager.Queue()

    # Creamos el proceso "listener" que mostrará la barra de progreso
    listener = Process(target=progress_listener, args=(len(all_files), progress_queue))
    listener.start()

    # Preparamos la lista de tareas para el Pool
    tasks = [(f, base_path, progress_queue) for f in all_files]

    # Procesamos en paralelo
    with Pool(processes=cpu_count()) as pool:
        results = pool.map(process_file, tasks)

    # Recolectamos los resultados
    for relative_path, content in results:
        if content is not None:
            files_with_content[relative_path] = content

    # Esperamos a que el proceso listener termine
    listener.join()
    return files_with_content

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Copies the content of all files in a folder to the clipboard, "
            "respecting .copyclipignore."
        ),
        epilog=(
            "Example usage:\n  python copyclip.py base_folder --extension .go\n\n"
            "The script looks for .copyclipignore in the same directory as this file, "
            "not where it's executed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "folder",
        nargs="?",
        default=".",
        help="Path to the base folder (default: current directory)."
    )
    parser.add_argument(
        "--extension",
        help="File extension to include, e.g., .go (optional).",
        default=None
    )

    args = parser.parse_args()
    base_path = os.path.abspath(args.folder)
    extension = args.extension

    if not os.path.exists(base_path):
        print(f"[ERROR] The folder {base_path} does not exist.")
        return

    # Localiza .copyclipignore en el mismo dir que este script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ignore_file_path = os.path.join(script_dir, ".copyclipignore")

    try:
        # 1) Escaneamos los archivos que SÍ se deben procesar
        all_files = scan_files(base_path, ignore_file_path, extension)
        if not all_files:
            print("[WARN] No files found to process based on the current filters.")
            return

        # 2) Leemos el contenido de esos archivos
        files_with_content = get_files_with_content(all_files, base_path)

        # 3) Copiamos su contenido al portapapeles
        print("[INFO] Preparing final clipboard content...")
        clipboard_content = []
        for relative_path, content in files_with_content.items():
            clipboard_content.append(f"{relative_path}:\n{content}")
        final_clipboard_text = "\n\n".join(clipboard_content)

        print("[INFO] Copying to clipboard...")
        pyperclip.copy(final_clipboard_text)
        print("[INFO] Content has been copied to the clipboard.")
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
