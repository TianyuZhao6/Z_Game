using UnityEngine;
using ZGame.UnityDraft.Combat;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple radial blast ability for the player. Damages enemies in range and applies slow/paint if set.
    /// </summary>
    public class PlayerBlast : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public BulletCombatSystem combat;
        public float radius = 2.5f;
        public int damage = 20;
        public float cooldown = 6f;
        public float slowAmount = 0.3f;
        public float slowDuration = 2f;
        public bool applyPaint = false;
        public bool applyAcid = false;
        public bool knockback = false;
        public float knockbackForce = 4f;
        public bool leavePaintAtOrigin = false;
        public bool inheritPlayerCrit = true;
        public bool applyVulnerabilityOnCrit = true;
        public float vulnMult = 1.2f;
        public float vulnDuration = 2f;
        public HUDController hud;
        private PaintSystem _paint;
        private float _cd;
        private Player _player;

        private void Awake()
        {
            if (combat == null) combat = FindObjectOfType<BulletCombatSystem>();
            _player = GetComponent<Player>();
            _paint = FindObjectOfType<PaintSystem>();
            if (hud == null) hud = FindObjectOfType<HUDController>();
        }

        private void Update()
        {
            _cd = Mathf.Max(0f, _cd - Time.deltaTime);
            if (hud != null) hud.SetAbilityCooldown("blast", _cd, cooldown);
            if (Input.GetKeyDown(KeyCode.Q) && _cd <= 0f)
            {
                Cast();
            }
        }

        private void Cast()
        {
            _cd = cooldown;
            if (leavePaintAtOrigin && _paint != null) _paint.SpawnEnemyPaint(transform.position, radius * 0.8f, slowDuration, _paint.paintColor);
            var hits = Physics2D.OverlapCircleAll(transform.position, radius, combat != null ? combat.enemyMask : LayerMask.GetMask("Enemy"));
            foreach (var h in hits)
            {
                var e = h.GetComponentInParent<Enemy>();
                if (e == null) continue;
                int dealt = damage;
                if (inheritPlayerCrit && _player != null)
                {
                    // basic crit roll
                    if (Random.value < _player.critChance)
                    {
                        dealt = Mathf.RoundToInt(dealt * _player.critMult);
                        if (applyVulnerabilityOnCrit) StatusEffect.ApplyVulnerability(e.gameObject, vulnMult, vulnDuration);
                    }
                }
                e.Damage(dealt);
                if (slowAmount > 0f) StatusEffect.ApplySlow(e.gameObject, slowAmount, slowDuration);
                if (applyPaint) StatusEffect.ApplyPaint(e.gameObject, slowDuration);
                if (applyAcid) StatusEffect.ApplyAcid(e.gameObject, damagePerSecond:5, duration:2f);
                if (knockback)
                {
                    var rb = e.GetComponent<Rigidbody2D>();
                    if (rb != null)
                    {
                        Vector2 dir = (e.transform.position - transform.position).normalized;
                        rb.AddForce(dir * knockbackForce, ForceMode2D.Impulse);
                    }
                }
            }
        }
    }
}
