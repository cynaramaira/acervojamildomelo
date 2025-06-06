import os
import re
import json
from html.parser import HTMLParser

# Define o diretório onde seus posts estão (relativo à localização do script)
POSTS_DIR = 'content/posts'

class HTMLCharacterDecoder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.decoded_data = ""

    def handle_entityref(self, name):
        import html
        try:
            self.decoded_data += html.unescape(f"&{name};")
        except:
            self.decoded_data += f"&{name};"
    
    def handle_charref(self, name):
        try:
            if name.startswith('x'):
                self.decoded_data += chr(int(name[1:], 16))
            else:
                self.decoded_data += chr(int(name))
        except:
            self.decoded_data += f"&{name};"
    
    def handle_data(self, data):
        self.decoded_data += data

    def decode_html_entities(self, text):
        self.decoded_data = ""
        if text:
            self.feed(text)
        self.close()
        return self.decoded_data

# Função para decodificar escapes Unicode literais (ex: \u00e9)
def decode_unicode_escapes(text):
    if not isinstance(text, str):
        return text
    try:
        # Tenta decodificar escapes Unicode literais na string
        return text.encode('latin1').decode('unicode_escape')
    except (UnicodeDecodeError, AttributeError):
        return text 

# Função para limpeza de strings para exibição no YAML (apenas para o título)
def clean_for_yaml_display(text):
    if text is None:
        return ""
    
    text = decode_unicode_escapes(str(text))

    decoder = HTMLCharacterDecoder()
    decoded_text = decoder.decode_html_entities(text)

    temp_text = re.sub(r'<br\s*/?>', ' ', decoded_text, flags=re.IGNORECASE)
    temp_text = re.sub(r'<[^>]+>', ' ', temp_text)
    
    normalized_text = temp_text.replace('\\\\', '\\') 
    final_text = re.sub(r'\s+', ' ', normalized_text).strip()

    # Escapar aspas duplas internas para YAML.
    # O YAML interpreta aspas duplas dentro de strings entre aspas duplas como literais se escapadas.
    escaped_text = final_text.replace('"', '\\"')
    
    return escaped_text


# Função para limpeza de strings para JSON-LD
def clean_for_json_ld(text):
    if text is None:
        return ""
    
    text = decode_unicode_escapes(str(text))

    decoder = HTMLCharacterDecoder()
    decoded_text = decoder.decode_html_entities(text)

    temp_text = re.sub(r'<br\s*/?>', ' ', decoded_text, flags=re.IGNORECASE)
    temp_text = re.sub(r'<[^>]+>', ' ', temp_text)
    
    normalized_text = temp_text.replace('\\\\', '\\')
    normalized_text = normalized_text.replace('\\"', '"') 

    final_clean_text = re.sub(r'\s+', ' ', normalized_text).strip()
    
    # IMPORTANTE: Agora, o json.dumps irá gerar uma string JSON válida, incluindo as aspas.
    # O Hugo/seu tema deve consumir isso como uma string dentro do JSON-LD.
    # Se você ainda precisa de um valor que não seja uma string JSON (ex: número, booleano),
    # o json.dumps por si só faz isso, mas aqui estamos assumindo que tudo é string.
    # Se o texto for vazio, json.dumps retornará '""'. Isso é um JSON válido.
    return json.dumps(final_clean_text, ensure_ascii=False)


def fix_markdown_file(filepath):
    print(f"Processando: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    front_matter_match = re.match(r'---\n(.*?)\n---(.*)', content, re.DOTALL)

    front_matter_str = ""
    markdown_body = ""
    if front_matter_match:
        front_matter_str = front_matter_match.group(1)
        markdown_body = front_matter_match.group(2).strip() 
    else:
        front_matter_str = ""
        markdown_body = content.strip()

    original_markdown_body = markdown_body 
    made_changes = False

    # --- CORREÇÕES NO CORPO DO MARKDOWN/HTML ---
    decoder = HTMLCharacterDecoder()
    
    # PASSO 1: Decodificar todas as entidades HTML no corpo PRIMEIRO
    temp_body = decoder.decode_html_entities(markdown_body)

    # PASSO 2: Tratar quebras de linha HTML e blocos como parágrafos Markdown
    temp_body = re.sub(r'<br\s*/?>', '\n', temp_body, flags=re.IGNORECASE)

    block_tags = ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'pre', 'table', 'tr', 'td', 'th']
    
    for tag in block_tags:
        temp_body = re.sub(rf'<{tag}[^>]*>', '\n\n', temp_body, flags=re.IGNORECASE)
        temp_body = re.sub(rf'</{tag}>', '\n\n', temp_body, flags=re.IGNORECASE)
    
    # PASSO 3: Remover tags HTML remanescentes que não são de bloco e não devem ser interpretadas
    temp_body = re.sub(r'<[^>]+>', '', temp_body)

    # PASSO 4: Normalizar quebras de linha para apenas 2 entre blocos de parágrafos
    temp_body = re.sub(r'\n\s*\n+', '\n\n', temp_body) 
    
    temp_body = re.sub(r'[ \t]+$', '', temp_body, flags=re.MULTILINE)

    temp_body = re.sub(r'^[ \t]+', '', temp_body, flags=re.MULTILINE)
    
    temp_body = re.sub(r' {2,}', ' ', temp_body)

    temp_body = re.sub(r'^\s*$', '', temp_body, flags=re.MULTILINE)

    temp_body = temp_body.strip() 

    if temp_body != markdown_body:
        markdown_body = temp_body
        made_changes = True

    # --- Processar e Sanitizar Title no Front Matter (IGNORA DESCRIPTION) ---
    front_matter_lines = front_matter_str.split('\n')
    new_front_matter_lines = []
    
    current_front_matter_dict = {}
    
    for line in front_matter_lines:
        if ':' in line:
            key, value = line.split(':', 1)
            current_front_matter_dict[key.strip()] = value.strip()

    original_title = current_front_matter_dict.get('title', 'Título não encontrado').strip('"').strip("'")
    sanitized_title_for_yaml = clean_for_yaml_display(original_title)
    
    found_title_in_loop = False 
    
    for line in front_matter_lines:
        stripped_line = line.strip()
        if stripped_line.startswith('title:'):
            new_front_matter_lines.append(f'title: "{sanitized_title_for_yaml}"')
            if original_title != sanitized_title_for_yaml:
                made_changes = True
            found_title_in_loop = True
        elif stripped_line.startswith('description:'):
            new_front_matter_lines.append(line) 
        else:
            new_front_matter_lines.append(line)
    
    if not found_title_in_loop:
        new_front_matter_lines.insert(0, f'title: "{sanitized_title_for_yaml}"')
        made_changes = True

    new_front_matter_str = '\n'.join(new_front_matter_lines)


    # --- Determinar a descrição para o JSON-LD (mantida separada) ---
    description_for_json_ld = ""
    if 'description' in current_front_matter_dict and current_front_matter_dict['description'].lower() != 'null':
        description_for_json_ld = current_front_matter_dict['description'].strip('"').strip("'")
        description_for_json_ld = clean_for_json_ld(description_for_json_ld) 
    elif original_markdown_body:
        temp_summary_for_json_ld = decoder.decode_html_entities(original_markdown_body)
        temp_summary_for_json_ld = re.sub(r'<br\s*/?>', ' ', temp_summary_for_json_ld, flags=re.IGNORECASE)
        temp_summary_for_json_ld = re.sub(r'<[^>]+>', ' ', temp_summary_for_json_ld)
        temp_summary_for_json_ld = re.sub(r'\s+', ' ', temp_summary_for_json_ld).strip()
        description_for_json_ld = temp_summary_for_json_ld[:200]
        if len(temp_summary_for_json_ld) > 200:
            description_for_json_ld += "..."
        description_for_json_ld = clean_for_json_ld(description_for_json_ld) 
    else:
        description_for_json_ld = clean_for_json_ld(original_title) 


    # --- SIMULAÇÃO DE JSON-LD ---
    mock_json_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": clean_for_json_ld(original_title),
        "description": description_for_json_ld,
        "datePublished": clean_for_json_ld(current_front_matter_dict.get('date', '2000-01-01T00:00:00Z')),
        "author": {
            "@type": "Person",
            "name": clean_for_json_ld(current_front_matter_dict.get('author', 'Autor Desconhecido'))
        }
    }

    try:
        # AQUI VAMOS USAR json.dumps no dicionário inteiro, que é o mais seguro.
        # Ele vai garantir que todas as strings internas sejam escapadas corretamente.
        json_output = json.dumps(mock_json_ld, indent=2, ensure_ascii=False)
    except json.JSONDecodeError as e:
        print(f"  !!! Erro de JSON-LD simulado para {filepath}: {e}")
        print(f"  Detalhes do erro JSON: {e}")
        print(f"  Parte do JSON que pode estar com problema:")
        print(f"  Headline (para JSON): '{clean_for_json_ld(original_title)}'")
        print(f"  Description (para JSON): '{description_for_json_ld}'")
        print(f"  Original Title (no MD, após HTML decode): '{original_title}'")
        print(f"  Original Description Content (no MD, após HTML decode): '{description_for_json_ld}'")
        print("-" * 40)
        return False

    # --- SALVAR O ARQUIVO APÓS CORREÇÕES (se houver) ---
    if made_changes:
        if front_matter_match:
            new_content = f"---\n{new_front_matter_str}\n---\n\n{markdown_body}"
        else:
            new_content = f'---\ntitle: "{sanitized_title_for_yaml}"\n---\n\n{markdown_body}'

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"  --> Corrigido e salvo: {filepath}")
        return True
    else:
        print(f"  --> Nenhuma alteração necessaria.")
        return False


def main():
    corrected_files_count = 0
    
    print(f"Iniciando o processamento de todos os arquivos Markdown em: {POSTS_DIR}")
    
    for root, _, files in os.walk(POSTS_DIR):
        for file in files:
            if file.endswith('.md'):
                filepath = os.path.join(root, file)
                if fix_markdown_file(filepath):
                    corrected_files_count += 1
    
    print(f"\nProcessamento concluido. Total de arquivos corrigidos: {corrected_files_count}")

if __name__ == "__main__":
    main()