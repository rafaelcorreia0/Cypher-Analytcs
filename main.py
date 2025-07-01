#v0.1



# --- Importações ---
import requests
import time
# --- Configuração ---
API_KEY = "Sua chave de api HenrikDev ou Crie um .env se for usar isso publicamente"
TEMPO_MAX_TRADE_MS = 7000


# --- Módulo de Entrada (API) ---
def buscar_partida_analisavel(regiao, nome_usuario, tag):
    """
    Busca a última partida que seja do modo 'Competitivo'
    """
    headers = {'Authorization': API_KEY}
    try:
        print(f"Buscando PUUID para {nome_usuario}#{tag}...")
        url_conta = f"https://api.henrikdev.xyz/valorant/v1/account/{nome_usuario}/{tag}"
        resp_conta = requests.get(url_conta, headers=headers)
        resp_conta.raise_for_status()
        dados_conta = resp_conta.json()
        puuid = dados_conta['data']['puuid']

        print("Buscando histórico de partidas para encontrar uma análise válida...")
        url_hist_partidas = f"https://api.henrikdev.xyz/valorant/v3/by-puuid/matches/{regiao}/{puuid}"
        # Pedimos um número maior de partidas para ter mais chance de achar uma competitiva
        params_partidas = {'size': 25}
        resp_hist_partidas = requests.get(url_hist_partidas, params=params_partidas, headers=headers)
        resp_hist_partidas.raise_for_status()
        dados_hist_partidas = resp_hist_partidas.json()

        partida_competitiva = None
        for partida_resumo in dados_hist_partidas.get('data', []):
            if partida_resumo.get('metadata', {}).get('mode', '').lower() == 'competitive':
                partida_competitiva = partida_resumo
                break
            else:
                print(
                    f"Ignorando partida recente do modo '{partida_resumo.get('metadata', {}).get('mode', 'Desconhecido')}'...")


        if not partida_competitiva:
            print("Não foi encontrada nenhuma partida do modo 'Competitive' nas suas últimas 10 partidas.")
            return None, None

        id_partida = partida_competitiva['metadata']['matchid']
        print(f"Partida competitiva encontrada (ID: {id_partida}). Buscando relatório de batalha...")

        url_detalhes = f"https://api.henrikdev.xyz/valorant/v2/match/{id_partida}"
        resp_detalhes = requests.get(url_detalhes, headers=headers)
        resp_detalhes.raise_for_status()
        dados_detalhados = resp_detalhes.json()

        if dados_detalhados.get('status') == 200:
            print("Relatório recebido com sucesso.")
            return dados_detalhados['data'], puuid
        return None, None

    except Exception as e:
        print(f"Ocorreu um erro inesperado durante a busca de dados: {e}")
        return None, None



def analisar_relatorio_de_batalha(dados_partida, puuid_jogador):
    """Analisa e calcula todas as métricas de desempenho da partida."""
    jogador_info = next((p for p in dados_partida['players']['all_players'] if p['puuid'] == puuid_jogador), None)
    if not jogador_info: return None

    #Pega o placar da seção 'metadata', que é mais confiável.
    metadata = dados_partida['metadata']
    times = dados_partida['teams']
    meu_time = 'Red' if jogador_info['team'].lower() == 'red' else 'Blue'
    placar_partida = f"{times[meu_time]['rounds_won']}-{times[meu_time]['rounds_lost']}" if times.get(
        meu_time) else "N/A"

    # Métricas diretas e rank
    stats = jogador_info['stats']
    kills = stats.get('kills', 0)
    deaths = stats.get('deaths', 0)
    assists = stats.get('assists', 0)
    score = stats.get('score', 0)
    rank = jogador_info.get('currenttier_patched', 'Unrated')

    #Cálculo de RR (TRS)
    rank_info = dados_partida.get('players', {}).get('all_players', [{}])[0].get('currenttier', 0) #vou usar futuramente, mas no momento nao esta em uso
    mudanca_rank = 0
    if 'tier_progress_after_update' in jogador_info:
        mudanca_rank = jogador_info.get('tier_progress_after_update', 0) - jogador_info.get(
            'tier_progress_before_update', 0)
    trs_string = f"+{mudanca_rank}" if mudanca_rank > 0 else str(mudanca_rank)

    # Cálculos por rodada
    rodadas_jogadas = metadata.get('rounds_played', 0)
    if rodadas_jogadas == 0: return None

    acs = round(score / rodadas_jogadas)
    kd_ratio = round(kills / deaths, 2) if deaths > 0 else float(kills)

    # Pega o dano do nível correto do objeto
    dano_total = jogador_info.get('damage_made', 0)
    adr = round(dano_total / rodadas_jogadas)
    dano_recebido = jogador_info.get('damage_received', 0)
    dd_delta = dano_total - dano_recebido

    tiros_na_cabeca = stats.get('headshots', 0)
    total_tiros = stats.get('bodyshots', 0) + stats.get('legshots', 0) + tiros_na_cabeca
    hs_percent = round((tiros_na_cabeca / total_tiros) * 100) if total_tiros > 0 else 0

    # Cálculos(KAST, FK/FD, MK)
    first_kills_totais = 0
    first_deaths_totais = 0
    rounds_com_impacto_kast = 0
    multi_kills = {'2k': 0, '3k': 0, '4k': 0, '5k': 0}

    for numero_rodada in range(1, rodadas_jogadas + 1):
        kills_desta_rodada = [k for k in dados_partida.get('kills', []) if k.get('round') == numero_rodada]

        minhas_kills_na_rodada = [k for k in kills_desta_rodada if k['killer_puuid'] == puuid_jogador]
        minhas_assists_na_rodada = [k for k in kills_desta_rodada for a in k.get('assistants', []) if
                                    a.get('assistant_puuid') == puuid_jogador]
        minha_morte_na_rodada = next((k for k in kills_desta_rodada if k['victim_puuid'] == puuid_jogador), None)

        num_kills_rodada = len(minhas_kills_na_rodada)
        if num_kills_rodada >= 2:
            key = f'{min(num_kills_rodada, 5)}k'
            if key in multi_kills: multi_kills[key] += 1

        sobreviveu = minha_morte_na_rodada is None
        trade = False
        if minha_morte_na_rodada:
            assassino_puuid = minha_morte_na_rodada['killer_puuid']
            for kill_vinganca in kills_desta_rodada:
                if (kill_vinganca['killer_team'] == minha_morte_na_rodada['victim_team'] and
                        kill_vinganca['victim_puuid'] == assassino_puuid and
                        kill_vinganca['kill_time_in_round'] > minha_morte_na_rodada['kill_time_in_round'] and
                        #########################################################################################
                        (kill_vinganca['kill_time_in_round'] - minha_morte_na_rodada[
                            'kill_time_in_round']) <= TEMPO_MAX_TRADE_MS):
                    trade = True
                    break

        if minhas_kills_na_rodada or minhas_assists_na_rodada or sobreviveu or trade:
            rounds_com_impacto_kast += 1

        if kills_desta_rodada:
            primeiro_abate = min(kills_desta_rodada, key=lambda k: k['kill_time_in_round'])
            if primeiro_abate['killer_puuid'] == puuid_jogador: first_kills_totais += 1
            if primeiro_abate['victim_puuid'] == puuid_jogador: first_deaths_totais += 1

    kast_percentual = round((rounds_com_impacto_kast / rodadas_jogadas) * 100)

    return {
        'rank': rank, 'trs': trs_string, 'placar': placar_partida, 'acs': acs,
        'k': kills, 'd': deaths, 'a': assists, 'mais_menos': kills - deaths,
        'kd': kd_ratio, 'dd_delta': round(dd_delta / rodadas_jogadas), 'adr': adr,
        'hs_percent': hs_percent, 'kast': kast_percentual, 'fk': first_kills_totais,
        'fd': first_deaths_totais, 'multi_kills': multi_kills
    }


# --- Interface de Saída
def gerar_relatorio_completo(relatorio):
    if not relatorio: return
    mk_string = " | ".join(
        [f"{count}x{tipo}" for tipo, count in relatorio['multi_kills'].items() if count > 0]) or "Nenhum"
    print("\n" + "=" * 55)
    print("||" + "RELATÓRIO DE BATALHA".center(51) + "||")
    print("=" * 55)
    print(f" Placar Final: {relatorio['placar']}".ljust(54) + "||")
    print(f" {'-' * 53}".ljust(54) + "||")
    print(f" Rank: {relatorio['rank']} ({relatorio['trs']} RR)".ljust(54) + "||")
    print(f" ACS: {relatorio['acs']}".ljust(54) + "||")
    print(f" KDA: {relatorio['k']} / {relatorio['d']} / {relatorio['a']} (KDA: {relatorio['kd']})".ljust(54) + "||")
    print(f" +/-: {relatorio['mais_menos']}".ljust(54) + "||")
    print(f" ADR: {relatorio['adr']}".ljust(54) + "||")
    print(f" HS%: {relatorio['hs_percent']}%".ljust(54) + "||")
    print(f" KAST: {relatorio['kast']}%".ljust(54) + "||")
    print(f" DDΔ/round: {relatorio['dd_delta']}".ljust(54) + "||")
    print(f" FK/FD: {relatorio['fk']} / {relatorio['fd']}".ljust(54) + "||")
    print(f" Multi-Kills: {mk_string}".ljust(54) + "||")
    print("=" * 55)


# --- Função Principal ---
def main():
    print("Bem-vindo ao Coach de Valorant v0.1 (O Coach Inteligente ou Tentando)!")
    regiao = input("Digite sua região (ex: br, na, eu, ap, kr): ").lower()
    nome_usuario = input("Digite seu nome de usuário do Valorant (sem a tag): ")
    tag = input("Digite sua tag (apenas os números, sem o #): ")

    dados_partida, puuid_jogador = buscar_partida_analisavel(regiao, nome_usuario, tag)

    if dados_partida and puuid_jogador:
        relatorio = analisar_relatorio_de_batalha(dados_partida, puuid_jogador)
        if relatorio:
            gerar_relatorio_completo(relatorio)


if __name__ == "__main__":
    main()
