using UnityEngine;
using ZGame.UnityDraft.Pathfinding;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple teleport with targeting/validation against blocked grid.
    /// </summary>
    public class PlayerTeleport : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public GridManager grid;
        public float maxRange = 6f;
        public KeyCode teleportKey = KeyCode.E;
        public bool requireClearLine = true;
        public bool requireTargetUnblocked = true;
        public float cooldown = 2f;
        public GameObject failVfx;
        public AudioClip failSfx;
        private float _cd;

        private void Awake()
        {
            if (grid == null) grid = FindObjectOfType<GridManager>();
        }

        private void Update()
        {
            _cd = Mathf.Max(0f, _cd - Time.deltaTime);
            if (Input.GetKeyDown(teleportKey))
            {
                TryTeleport();
            }
        }

        private void TryTeleport()
        {
            if (_cd > 0f) return;
            Vector3 mouse = Camera.main != null ? Camera.main.ScreenToWorldPoint(Input.mousePosition) : transform.position;
            mouse.z = 0f;
            Vector3 dir = mouse - transform.position;
            if (dir.magnitude > maxRange) dir = dir.normalized * maxRange;
            Vector3 targetPos = transform.position + dir;
            if (IsValid(targetPos))
            {
                transform.position = targetPos;
                _cd = cooldown;
            }
            else
            {
                if (failVfx != null) Instantiate(failVfx, transform.position, Quaternion.identity);
                if (failSfx != null) AudioSource.PlayClipAtPoint(failSfx, transform.position);
            }
        }

        private bool IsValid(Vector3 pos)
        {
            if (grid != null)
            {
                if (requireTargetUnblocked && grid.IsBlocked(pos)) return false;
                if (requireClearLine && !LineIsClear(transform.position, pos)) return false;
            }
            return true;
        }

        private bool LineIsClear(Vector3 start, Vector3 end)
        {
            if (grid == null) return true;
            float step = balance != null ? balance.cellSize * 0.5f : 0.5f;
            float dist = Vector3.Distance(start, end);
            int samples = Mathf.Max(1, Mathf.CeilToInt(dist / step));
            Vector3 dir = (end - start).normalized;
            for (int i = 1; i <= samples; i++)
            {
                Vector3 p = start + dir * (i * step);
                if (grid.IsBlocked(p)) return false;
            }
            return true;
        }
    }
}
