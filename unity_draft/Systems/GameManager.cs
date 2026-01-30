using UnityEngine;
using System;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// High-level game state coordinator: level start/end, boss flags, twin boss toggle, bandit spawn toggle, biome buffs stub.
    /// This is a scaffold; hook up your scene/UI and level configs.
    /// </summary>
    public class GameManager : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public LevelFlow levelFlow;
        public MetaProgression meta;
        public HUDController hud;
        public UI.MenuController menu;
        public LevelSession session;

        [Header("Runtime State")]
        public int currentLevelIndex = 0; // 0-based
        public bool bossLevel = false;
        public bool twinBoss = false;
        public bool banditAllowed = false;
        public string biome = null;

        public event Action OnLevelStarted;
        public event Action OnLevelCompleted;
        public event Action OnLevelFailed;

        private void Awake()
        {
            if (levelFlow == null) levelFlow = GetComponent<LevelFlow>();
            if (meta == null) meta = GetComponent<MetaProgression>();
            if (hud == null) hud = FindObjectOfType<HUDController>();
            if (menu == null) menu = FindObjectOfType<UI.MenuController>();
            if (session == null) session = FindObjectOfType<LevelSession>();
        }

        public void StartLevel(int levelIdx)
        {
            currentLevelIndex = levelIdx;
            bossLevel = levelFlow != null && levelFlow.IsBossLevel(levelIdx);
            twinBoss = levelFlow != null && levelFlow.UseTwinBoss(levelIdx);
            banditAllowed = levelFlow != null && levelFlow.ShouldSpawnBandit(levelIdx);
            biome = levelFlow != null ? levelFlow.NextBiome(levelIdx) : null;
            levelFlow?.ApplyBiomeBuffs(biome, balance);
            OnLevelStarted?.Invoke();
            menu?.HideStartSequence();
            hud?.SetTimer(session != null ? session.levelTime : 0f);
            menu?.BindMeta(meta, this);
        }

        public void CompleteLevel()
        {
            Time.timeScale = 0f;
            meta?.OnLevelComplete(currentLevelIndex);
            OnLevelCompleted?.Invoke();
            menu?.ShowSuccess();
        }

        public void FailLevel()
        {
            Time.timeScale = 0f;
            OnLevelFailed?.Invoke();
            menu?.ShowFail();
        }
    }
}
