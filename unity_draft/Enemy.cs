using UnityEngine;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Minimal enemy prototype using current Python balance values.
    /// Hook this up to your spawn system and movement/AI later.
    /// </summary>
    [RequireComponent(typeof(SpriteRenderer))]
    public class Enemy : MonoBehaviour, ICritSource
    {
        [Header("Config")]
        public EnemyTypeConfig typeConfig;
        public GameBalanceConfig balance;

        [Header("Runtime State")]
        public int hp;
        public int maxHp;
        public int attack;
        public float speed;
        public int shieldHp; // for shielder buffs
        public int spoils;          // coins held
        public int coinsAbsorbed;   // total absorbed
        public float baseSizePx;    // unscaled footprint in world px (e.g., cellSize * 0.6)
        public float critChance = 0.0f;
        public float critMult = 1.0f;
        public System.Action OnKilled;

        private SpriteRenderer _sr;
        private Collider2D _collider;

        private void Awake()
        {
            _sr = GetComponent<SpriteRenderer>();
            _collider = GetComponent<Collider2D>();
        }

        public void Init(GameBalanceConfig bal, EnemyTypeConfig cfg, float cellSize)
        {
            balance = bal;
            typeConfig = cfg;

            float baseFootprint = cellSize * 0.6f * cfg.sizeMultiplier;
            baseSizePx = baseFootprint;
            maxHp = Mathf.Max(1, cfg.baseHp);
            hp = maxHp;
            attack = Mathf.Max(1, cfg.attack);
            speed = cfg.speed;
            critChance = cfg.critChance;
            critMult = cfg.critMult;

            ApplyCoinAbsorbScale(); // set initial scale (no coins → 1.0)

            if (_sr != null)
            {
                _sr.color = cfg.color;
                if (cfg.sprite) _sr.sprite = cfg.sprite;
            }
        }

        public void AddSpoils(int amount)
        {
            int n = Mathf.Max(0, amount);
            if (n <= 0) return;

            spoils += n;
            coinsAbsorbed += n;

            // HP gain per coin
            maxHp += balance.spoilHpPer * n;
            hp = Mathf.Min(maxHp, hp + balance.spoilHpPer * n);

            // Attack threshold
            if (spoils % balance.spoilAtkStep == 0)
                attack += 1;

            // Speed threshold
            if (spoils % balance.spoilSpdStep == 0)
                speed = Mathf.Min(balance.spoilSpdCap, speed + balance.spoilSpdAdd);

            ApplyCoinAbsorbScale();
        }

        private void ApplyCoinAbsorbScale()
        {
            float scale = CoinAbsorbScale(coinsAbsorbed);
            float size = Mathf.Max(2f, baseSizePx * scale);
            // Visual scale: assume sprite pixel density matches world units; adjust if you map differently.
            transform.localScale = new Vector3(scale, scale, 1f);
            // If you tie collider size to visuals, also resize colliders here.
            if (_collider is CircleCollider2D cc)
            {
                cc.radius = size * 0.5f;
            }
        }

        public void Damage(int dmg)
        {
            var status = GetComponent<ZGame.UnityDraft.Systems.StatusEffect>();
            if (status != null) status.TryAbsorb(ref dmg);
            hp = Mathf.Max(0, hp - Mathf.Max(0, dmg));
            if (hp <= 0)
            {
                Kill();
            }
        }

        public void Kill()
        {
            if (hp > 0) hp = 0;
            OnKilled?.Invoke();
            gameObject.SetActive(false);
        }

        private float CoinAbsorbScale(int coins)
        {
            int c1 = balance.coinTier1Max;
            int c2 = balance.coinTier2Max;
            float s1 = balance.coinScaleTier1;
            float s2 = balance.coinScaleTier2;
            float s3 = balance.coinScaleTier3;

            if (coins <= 0 || c1 <= 0) return 1f;
            if (coins < c1)
            {
                float t = coins / (float)c1;
                return Mathf.Lerp(1f, s1, t);
            }
            if (coins < c2)
            {
                float t = (coins - c1) / Mathf.Max(1f, (float)(c2 - c1));
                return Mathf.Lerp(s1, s2, t);
            }
            // Tier 3: grow toward cap over +10 coins (soft ramp), clamp to s3.
            float t3 = Mathf.Clamp01((coins - c2) / 10f);
            return Mathf.Min(s3, Mathf.Lerp(s2, s3, t3));
        }
    }
}
