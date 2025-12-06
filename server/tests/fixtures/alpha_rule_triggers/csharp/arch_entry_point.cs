// Should trigger: arch.entry_point
using Microsoft.AspNetCore.Mvc;

namespace MyApp.Controllers
{
    // ASP.NET Core controller - HTTP entry points
    [ApiController]
    [Route("api/[controller]")]
    public class UsersController : ControllerBase
    {
        [HttpGet]
        public IActionResult GetUsers()
        {
            return Ok(new { users = new string[0] });
        }

        [HttpPost]
        public IActionResult CreateUser([FromBody] object body)
        {
            return Ok(new { created = true });
        }
    }
    
    // Main entry point
    public class Program
    {
        public static void Main(string[] args)
        {
            Console.WriteLine("Starting application...");
        }
    }
}
