import json
import os
import re
from datetime import datetime, timezone
import unicodedata

def slugify(value):
    """
    Normaliza strings, converte para minúsculas, remove acentos,
    caracteres não-ASCII, espaços para hífens, e remove caracteres
    duplicados/inválidos para um slug.
    """
    value = str(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('utf-8')
    value = re.sub(r'[^\w\s-]', '', value).strip()
    value = re.sub(r'[-\s]+', '-', value)
    return value.lower()

def clean_html(raw_html):
    """
    Remove tags HTML e limpa espaços extras.
    """
    if raw_html is None:
        return None
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.strip()

def format_yaml_value(value):
    """
    Formata um valor para ser seguro para YAML.
    Usa json.dumps para strings e converte None para 'null' YAML.
    """
    if value is None:
        return 'null'
    if isinstance(value, str):
        # json.dumps adiciona as aspas e escapa caracteres especiais
        return json.dumps(value)
    return str(value) # Para números, booleanos, etc.

def processar_postagens_por_ano(arquivos_json, ano_filtrar, pasta_destino_base):
    """
    Lê os arquivos JSON fornecidos, filtra as postagens por ano,
    limpa os títulos e salva cada postagem em um arquivo Markdown
    dentro da pasta _posts/ANO dentro da pasta de destino base.
    Também registra postagens com erros de data.
    """
    postagens_filtradas = []
    erros_data_postagens = [] # Lista para registrar posts com problemas de data

    for arquivo_json in arquivos_json:
        try:
            with open(arquivo_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if 'rows' in data and isinstance(data['rows'], list):
                for postagem in data['rows']:
                    data_publicacao_str = postagem.get('data_publicacao')
                    post_id = postagem.get('id', 'ID_Nao_Encontrada')

                    if not isinstance(data_publicacao_str, str) or not data_publicacao_str.strip():
                        erros_data_postagens.append({
                            'arquivo_json': arquivo_json,
                            'post_id': post_id,
                            'motivo': f"Data de publicação ausente ou não é uma string válida: '{data_publicacao_str}'"
                        })
                        continue
                    
                    try:
                        # Tenta parsear a data para verificar o ano, usando replace('Z', '+00:00') para flexibilidade
                        data_publicacao = datetime.fromisoformat(data_publicacao_str.replace('Z', '+00:00'))
                        ano_da_postagem = str(data_publicacao.year)
                        if ano_da_postagem == ano_filtrar:
                            postagens_filtradas.append(postagem)
                    except ValueError:
                        erros_data_postagens.append({
                            'arquivo_json': arquivo_json,
                            'post_id': post_id,
                            'motivo': f"Formato de data inválido: '{data_publicacao_str}'"
                        })
                        continue
            else:
                print(f"Aviso no arquivo '{arquivo_json}': Estrutura JSON inválida. Esperava 'rows' como lista.")
        except FileNotFoundError:
            print(f"Erro: Arquivo '{arquivo_json}' não encontrado.")
            continue
        except json.JSONDecodeError:
            print(f"Erro: Falha ao decodificar o JSON em '{arquivo_json}'. Verifique a estrutura do arquivo.")
            continue

    if not postagens_filtradas:
        print(f"Nenhuma postagem encontrada para o ano de {ano_filtrar} nos arquivos fornecidos.")
        return

    diretorio_ano = os.path.join(pasta_destino_base, '_posts', ano_filtrar)
    os.makedirs(diretorio_ano, exist_ok=True)

    for i, postagem in enumerate(postagens_filtradas):
        # --- Processar Tags ---
        tags_raw = postagem.get('materia_tags')
        tags_list = []
        if tags_raw and isinstance(tags_raw, str):
            tags_list = [slugify(tag) for tag in tags_raw.split(',') if tag.strip()]
        if not tags_list:
            tags_list.append("sem-tags")
        # Agora, formata a lista de tags para o YAML do Front Matter usando json.dumps para cada tag
        tags_formatted = "\n" + "\n".join([f"  - {format_yaml_value(tag)}" for tag in tags_list])

        # --- Processar Categorias ---
        categoria_raw = postagem.get('categoria')
        categories_list = []
        if categoria_raw and isinstance(categoria_raw, str):
            categories_list = [slugify(cat) for cat in str(categoria_raw).split(',') if cat.strip()]
        if not categories_list:
            categories_list.append("sem-categoria")
        categories_formatted = "\n" + "\n".join([f"  - {format_yaml_value(cat)}" for cat in categories_list])

        # --- Definir Título e Conteúdo ---
        post_title = postagem.get('title') or postagem.get('titulo')
        if not post_title:
            post_title = "Postagem sem Título"
            # Não registra aqui, pois o post será criado, só com título genérico

        post_content = postagem.get('conteudo') or ""

        # --- Formatar data para nome do arquivo e Front Matter ---
        data_publicacao_iso = postagem.get('data_publicacao')
        data_para_arquivo = "data-invalida"
        date_front_matter_iso = None # Usar None para valores nulos no YAML, será formatado por format_yaml_value

        if isinstance(data_publicacao_iso, str) and data_publicacao_iso.strip():
            try:
                data_obj_completa = datetime.fromisoformat(data_publicacao_iso.replace('Z', '+00:00'))
                data_para_arquivo = data_obj_completa.strftime('%Y-%m-%d')
                
                # Garante UTC para o Front Matter (Jekyll prefere)
                if data_obj_completa.tzinfo is None:
                    data_obj_completa = data_obj_completa.replace(tzinfo=timezone.utc)
                else:
                    data_obj_completa = data_obj_completa.astimezone(timezone.utc)

                date_front_matter_iso = data_obj_completa.isoformat(timespec='seconds').replace('+00:00', 'Z')
                
            except ValueError:
                pass # Erro já foi capturado na fase de filtragem

        # --- Gerar Nome do Arquivo Markdown com limite de 100 caracteres ---
        # A meta é que o NOME DO ARQUIVO COMPLETO (data-slug-id.md) não exceda 100 caracteres.
        # Caminho base: _posts/ANO/ = ~12 caracteres
        # Data: YYYY-MM-DD = 10 caracteres
        # ID: -12345678.md = ~12 caracteres
        # Total fixo (aprox): 10 + 12 = 22 caracteres
        # Limite para o slug do título = 100 - 22 = 78 caracteres. Vamos usar 70 para ser seguro.

        post_unique_id = postagem.get('id', i+1) # Garantir um ID único ou fallback
        id_part_length = len(str(post_unique_id)) + 4 # -ID.md = 4 chars + ID length

        # Calcula o comprimento máximo para a parte do slug do título
        # 100 (total) - len(data_para_arquivo) - 1 (hifen) - id_part_length - 1 (hifen)
        # Deixa uma pequena margem (ex: -5) para segurança
        MAX_SLUG_CHARACTERS = 100 - len(data_para_arquivo) - id_part_length - 2 - 5 # 2 hifens, 5 margem
        if MAX_SLUG_CHARACTERS < 10: # Não deixar o slug ser ridiculamente pequeno
            MAX_SLUG_CHARACTERS = 10

        base_slug = slugify(post_title)
        
        # Corta o slug do título se for muito longo
        if len(base_slug) > MAX_SLUG_CHARACTERS:
            # Tenta cortar no último hífen antes do limite para não quebrar palavra
            truncated_slug = base_slug[:MAX_SLUG_CHARACTERS].rsplit('-', 1)[0]
            if not truncated_slug: # Fallback se o corte resultou em string vazia
                truncated_slug = "post" # Nome genérico bem curto
            base_slug = truncated_slug
        
        # Constrói o nome do arquivo final
        filename_slug = f"{data_para_arquivo}-{base_slug}-{post_unique_id}.md"

        # Verificação final para garantir que não excede 100 caracteres
        if len(filename_slug) > 100:
             # Isso só deve acontecer se a lógica acima falhar para casos extremos,
             # ou se data/id forem MUITO longos. Tenta cortar mais agressivamente.
            print(f"Aviso Crítico: Nome de arquivo ainda muito longo após corte: {filename_slug} (Tamanho: {len(filename_slug)})")
            # Corta do início, mantendo o final do ID e extensão
            filename_slug = filename_slug[:90] + "-" + str(post_unique_id) + ".md"
            print(f"  Tentando cortar para: {filename_slug}")


        caminho_arquivo = os.path.join(diretorio_ano, filename_slug)

        # --- Conteúdo YAML para o Front Matter do Jekyll ---
        conteudo_yaml_template = """---
id: {id}
date: {date_front_matter}
last_modified_at: {last_modified_at}
tags:{tags_formatted}
categories:{categories_formatted}
title: {title}
sutia: {sutia}
chapeu: {chapeu}
autor: {autor}
imagem: {imagem}
---
{content_placeholder}
"""
        # Preparar todos os valores usando a função format_yaml_value para segurança
        formatted_id = format_yaml_value(postagem.get('id'))
        formatted_date = format_yaml_value(date_front_matter_iso)
        formatted_last_modified = format_yaml_value(postagem.get('data_alteracao'))
        formatted_title = format_yaml_value(post_title)
        formatted_sutia = format_yaml_value(clean_html(postagem.get('sutia')))
        formatted_chapeu = format_yaml_value(clean_html(postagem.get('chapeu')))
        formatted_autor = format_yaml_value(postagem.get('autor', 'Desconhecido'))
        formatted_image = format_yaml_value(postagem.get('imagem')) # Assume que 'imagem' já é o caminho ou None

        # Formata o template do Front Matter.
        # Use um placeholder diferente para o conteúdo para evitar conflito com {% raw %}
        conteudo_front_matter = conteudo_yaml_template.format(
            id=formatted_id,
            date_front_matter=formatted_date,
            last_modified_at=formatted_last_modified,
            tags_formatted=tags_formatted,
            categories_formatted=categories_formatted,
            title=formatted_title,
            sutia=formatted_sutia,
            chapeu=formatted_chapeu,
            autor=formatted_autor,
            imagem=formatted_image,
            content_placeholder="" # Será preenchido com raw + content depois
        )
        
        # AGORA, envolva o conteúdo da postagem com {% raw %} e {% endraw %}
        # Isso é feito depois que o Python já processou o template do Front Matter.
        # As chaves duplas {{ e }} escapam as chaves literais para a f-string.
        # O símbolo % não precisa de escape com barra invertida dentro de uma f-string.
        final_markdown_content = f"{conteudo_front_matter.strip()}\n{{% raw %}}\n{post_content}\n{{% endraw %}}"

        try:
            with open(caminho_arquivo, 'w', encoding='utf-8') as outfile:
                outfile.write(final_markdown_content)
            print(f"Postagem salva em: {caminho_arquivo}")
        except Exception as e:
            print(f"Erro ao salvar o arquivo '{caminho_arquivo}': {e}")
            if "Filename too long" in str(e):
                print(f"  ERRO CRÍTICO: Nome de arquivo ainda muito longo para: {caminho_arquivo} (Tamanho: {len(caminho_arquivo)})")
                print("  Por favor, verifique o MAX_SLUG_CHARACTERS e o cálculo do nome do arquivo.")
            
    print(f"Processamento para o ano de {ano_filtrar} concluído. As postagens foram salvas na pasta '_posts/{ano_filtrar}' dentro do diretório do site.")

    # Relatório de erros de data para este ano
    if erros_data_postagens:
        print(f"\n--- ATENÇÃO: Postagens com erros de data para o ano {ano_filtrar} ---")
        for erro in erros_data_postagens:
            print(f"  - Arquivo: {erro['arquivo_json']}, ID: {erro['post_id']}, Motivo: {erro['motivo']}")
        print("--------------------------------------------------")
    else:
        print(f"Nenhum erro de data encontrado para o ano {ano_filtrar}.")

    return erros_data_postagens # Retorna a lista de erros para ser usada na main, se processar "todos"

if __name__ == "__main__":
    # Ajuste os caminhos para serem relativos ao script, se o script estiver na pasta constpythonjson
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Caminhos para os arquivos JSON
    json_files_dir = script_dir # Se os JSONs estão na mesma pasta do script
    # Ou: json_files_dir = os.path.join(script_dir, '..', 'constpythonjson') # Se o script estiver em outra pasta

    arquivos_json = [
        os.path.join(json_files_dir, 'MateriasJamildo1.json'),
        os.path.join(json_files_dir, 'MateriasJamildo2.json'),
        os.path.join(json_files_dir, 'MateriasJamildo3.json')
    ]
    
    # Caminho para a pasta raiz do seu site Jekyll (acervoj)
    pasta_site = os.path.join(script_dir, '..', 'acervoj')

    # Lista para coletar todos os erros de data de todos os anos
    todos_erros_data = []

    while True:
        ano_desejado = input("Digite o ano que você deseja processar (ex: 2009, 2010...) ou 'todos' para processar todos os anos encontrados: ").strip()
        
        if ano_desejado.lower() == 'todos':
            anos_encontrados = set()
            print("Escaneando arquivos JSON para encontrar todos os anos de publicação...")
            for arquivo in arquivos_json:
                try:
                    with open(arquivo, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if 'rows' in data and isinstance(data['rows'], list):
                            for postagem in data['rows']:
                                data_publicacao_str_scan = postagem.get('data_publicacao')
                                post_id_scan = postagem.get('id', 'ID_Nao_Encontrada')

                                if not isinstance(data_publicacao_str_scan, str) or not data_publicacao_str_scan.strip():
                                    todos_erros_data.append({
                                        'arquivo_json': arquivo,
                                        'post_id': post_id_scan,
                                        'motivo': f"Data de publicação ausente ou não é uma string válida: '{data_publicacao_str_scan}' (durante scan de anos)"
                                    })
                                    continue
                                try:
                                    data_publicacao_scan = datetime.fromisoformat(data_publicacao_str_scan.replace('Z', '+00:00'))
                                    anos_encontrados.add(str(data_publicacao_scan.year))
                                except ValueError:
                                    todos_erros_data.append({
                                        'arquivo_json': arquivo,
                                        'post_id': post_id_scan,
                                        'motivo': f"Formato de data inválido: '{data_publicacao_str_scan}' (durante scan de anos)"
                                    })
                                    continue
                        else:
                            print(f"Aviso no arquivo '{arquivo}': Estrutura JSON inválida. Esperava 'rows' como lista. Este arquivo será ignorado para a lista de anos.")
                except (FileNotFoundError, json.JSONDecodeError) as e:
                    print(f"Erro ao ler ou decodificar '{arquivo}': {e}. Este arquivo será ignorado para a lista de anos.")
                    continue

            if anos_encontrados:
                print(f"\nAnos encontrados para processamento: {', '.join(sorted(list(anos_encontrados)))}")
                for ano in sorted(list(anos_encontrados)):
                    print(f"\n--- Iniciando Processamento para o ano: {ano} ---")
                    # Chama a função e anexa os erros específicos daquele ano à lista principal
                    todos_erros_data.extend(processar_postagens_por_ano(arquivos_json, ano, pasta_site))
                
                print("\n--- Processamento de TODOS os anos concluído! ---")
                
                # Relatório final de todos os erros de data encontrados
                if todos_erros_data:
                    print("\n========== RELATÓRIO FINAL DE POSTAGENS COM ERROS DE DATA ==========")
                    for erro in todos_erros_data:
                        print(f"  - Arquivo: {erro['arquivo_json']}, ID: {erro['post_id']}, Motivo: {erro['motivo']}")
                    print("=====================================================================")
                else:
                    print("\nNenhum erro de data encontrado em nenhum dos arquivos JSON durante o processamento completo.")
                
                break
            else:
                print("Nenhum ano válido encontrado nos arquivos JSON especificados.")
                break

        elif ano_desejado.isdigit() and len(ano_desejado) == 4:
            print(f"\n--- Iniciando Processamento para o ano: {ano_desejado} ---")
            erros_do_ano = processar_postagens_por_ano(arquivos_json, ano_desejado, pasta_site)
            print(f"\n--- Processamento do ano {ano_desejado} concluído! ---")
            
            # Relatório de erros para o ano específico
            if erros_do_ano:
                print(f"\n--- ATENÇÃO: Postagens com erros de data para o ano {ano_desejado} ---")
                for erro in erros_do_ano:
                    print(f"  - Arquivo: {erro['arquivo_json']}, ID: {erro['post_id']}, Motivo: {erro['motivo']}")
                print("--------------------------------------------------")
            else:
                print(f"Nenhum erro de data encontrado para o ano {ano_desejado}.")
            
            break
        else:
            print("Entrada inválida. Por favor, digite um ano válido (ex: 2009) ou 'todos'.")/a