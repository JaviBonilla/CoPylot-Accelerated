// Direct C ABI smoke test for sanitizer/leak checks without Python runtime noise.
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
extern "C" {
void* sp_data_create();
bool sp_data_free(void*);
bool sp_set_string(void*, const char*, const char*);
bool sp_set_number(void*, const char*, double);
bool sp_generate_layout(void*, int);
bool sp_simulate(void*, int, bool);
double* sp_get_fluxmap(void*, int*, int*, int, int);
double* sp_detail_results(void*, int*, int*, double*, int, bool);
void _sp_free_var(double*);
}
static void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
struct Context {
    void* data = sp_data_create();
    ~Context() { if (data) sp_data_free(data); }
};
struct Array {
    double* data;
    ~Array() { if (data) _sp_free_var(data); }
};
int main() {
    try {
        Context c;
        require(c.data != nullptr, "context");
        require(sp_set_string(c.data, "ambient.0.weather_file", COPILOT_WEATHER), "weather");
        const char* keys[] = {"solarfield.0.q_des", "solarfield.0.des_sim_detail",
            "land.0.is_bounds_scaled", "land.0.is_bounds_fixed", "land.0.min_fixed_rad",
            "land.0.max_fixed_rad", "fluxsim.0.flux_model", "fluxsim.0.flux_time_type",
            "fluxsim.0.flux_solar_el_in", "fluxsim.0.aim_method"};
        const double values[] = {100., 1., 0., 1., 160., 850., 0., 0., 55., 0.};
        for (int i = 0; i < 10; ++i) require(sp_set_number(c.data, keys[i], values[i]), keys[i]);
        require(sp_generate_layout(c.data, 1), "generate_layout");
        for (int repeat = 0; repeat < 3; ++repeat) {
            require(sp_simulate(c.data, 1, true), "simulate");
            int rows = 0, cols = 0;
            Array flux{sp_get_fluxmap(c.data, &rows, &cols, 0, 0)};
            require(flux.data && rows == 25 && cols == 25, "flux shape");
            double sum = 0.;
            for (int j = 0; j < rows * cols; ++j) {
                require(std::isfinite(flux.data[j]), "flux finite"); sum += flux.data[j];
            }
            require(sum > 0., "positive flux");
            Array details{sp_detail_results(c.data, &rows, &cols, nullptr, 0, false)};
            require(details.data && rows > 0 && cols > 0, "details shape");
            for (int j = 0; j < rows * cols; ++j) require(std::isfinite(details.data[j]), "details finite");
        }
        std::cout << "native smoke PASS\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n'; return 1;
    }
}
