using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Moving hurricane vortex for Wind biome: grows, drifts, and applies spiral forces.
    /// Matches Python constants for radius/forces.
    /// </summary>
    public class Hurricane : MonoBehaviour
    {
        [Header("Scale (world px)")]
        public float startRadius = 62.4f;   // CELL_SIZE * 1.2 (with 52px cell)
        public float maxRadius = 312f;      // CELL_SIZE * 6.0
        public float growthRate = 8f;       // px/s
        public float rangeMult = 2.6f;      // influence radius multiplier

        [Header("Forces")]
        public float pullStrength = 180f;         // radial pull (px/s force proxy)
        public float pullGrowthMult = 2.0f;       // extra pull as vortex grows
        public float vortexPower = 450f;          // tangential force
        public float escapeSpeed = 3.8f;          // reduces pull if entity speed above this
        public float escapeSize = 52f;            // entities larger resist a bit

        [Header("Motion")]
        public float driftSpeedMin = 16f;
        public float driftSpeedMax = 40f;

        private float _radius;
        private float _ang;
        private float _vx;
        private float _vy;
        private float _boundMargin;
        private GridManager _grid;
        private GameBalanceConfig _bal;

        public void Init(GameBalanceConfig bal, GridManager grid, Vector3 pos)
        {
            _bal = bal;
            _grid = grid;
            transform.position = pos;
            float cs = bal != null ? bal.cellSize : 52f;
            _radius = startRadius > 0 ? startRadius : cs * 1.2f;
            maxRadius = maxRadius > 0 ? maxRadius : cs * 6f;
            _boundMargin = maxRadius * 1.2f;
            float ang = Random.Range(0f, Mathf.PI * 2f);
            float spd = Random.Range(driftSpeedMin, driftSpeedMax);
            _vx = Mathf.Cos(ang) * spd;
            _vy = Mathf.Sin(ang) * spd;
        }

        private void Update()
        {
            float dt = Time.deltaTime;
            // grow
            _radius = Mathf.Min(maxRadius, _radius + growthRate * dt);
            _ang += dt * 5f;

            // drift and bounce
            float cs = _bal != null ? _bal.cellSize : 52f;
            float mapW = (_bal != null ? _bal.gridSize : 32) * cs;
            float mapH = (_bal != null ? _bal.gridSize : 32) * cs;
            float minX = _boundMargin;
            float maxX = mapW - _boundMargin;
            float minY = (_bal != null ? _bal.infoBarHeight : 40f) + _boundMargin;
            float maxY = (_bal != null ? _bal.infoBarHeight : 40f) + mapH - _boundMargin;
            Vector3 p = transform.position;
            p.x += _vx * dt;
            p.y += _vy * dt;
            if (p.x < minX || p.x > maxX)
            {
                p.x = Mathf.Clamp(p.x, minX, maxX);
                _vx *= -1f;
            }
            if (p.y < minY || p.y > maxY)
            {
                p.y = Mathf.Clamp(p.y, minY, maxY);
                _vy *= -1f;
            }
            transform.position = p;

            ApplyVortex(dt);
        }

        private void ApplyVortex(float dt)
        {
            float effectRadius = _radius * rangeMult;
            Collider2D[] hits = Physics2D.OverlapCircleAll(transform.position, effectRadius, LayerMask.GetMask("Player", "Enemy"));
            foreach (var h in hits)
            {
                var rb = h.attachedRigidbody;
                if (rb == null) continue;
                var enemy = h.GetComponent<Enemy>();
                var player = h.GetComponent<Player>();

                Vector2 toCenter = (Vector2)(transform.position - rb.position);
                float dist = toCenter.magnitude + 0.001f;
                Vector2 dir = toCenter / dist;
                float grow = Mathf.Min(1f, _radius / Mathf.Max(1f, maxRadius));
                float pull = pullStrength * (1f + pullGrowthMult * grow);
                float tangential = vortexPower * grow;

                // escape reduction
                float resist = 1f;
                if (enemy != null && enemy.speed > escapeSpeed) resist *= 0.5f;
                if (player != null && player.speed > escapeSpeed) resist *= 0.5f;

                rb.AddForce(dir * pull * resist * dt, ForceMode2D.Force);
                Vector2 tan = new Vector2(-dir.y, dir.x);
                rb.AddForce(tan * tangential * resist * dt, ForceMode2D.Force);
            }
        }
    }
}
